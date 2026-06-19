"""
UUID v7 generator — thread-safe, monoton.

UUID v7 — vaqt-tartibli UUID (RFC 9562).
Xususiyatlari:
  - Millisekund Unix timestamp prefiks (vaqt bo'yicha tartiblash imkoni)
  - Offline klient ham generatsiya qila oladi (server bilan to'qnashuvsiz)
  - PostgreSQL UUID PK sifatida btree indeksga qulay (monoton o'sish)
  - Bir xil millisekund ichida rand_a (12-bit) counter sifatida ishlatiladi
    (monoton tartib kafolati); counter to'lib ketsa — keyingi ms ga o'tiladi.
  - threading.Lock bilan thread-safe.

Standart kutubxona uuid.uuid7() Python 3.13+ da — biz 3.12 uchun
qo'lda implementatsiya qilamiz (tashqi kutubxonasiz).
"""

import os
import threading
import time
import uuid

# ─── Ichki holat ────────────────────────────────────────────────────────────
_lock = threading.Lock()
_last_ts_ms: int = 0   # oxirgi ishlatilgan millisekund
_counter: int = 0       # bir xil ms ichida monoton counter (12-bit: 0–4095)

_COUNTER_MAX = 0xFFF    # 12-bit: 4095


def uuid7() -> uuid.UUID:
    """
    UUID v7 generatsiya qilish — thread-safe, monoton.

    Tuzilishi (RFC 9562):
      [48-bit unix_ts_ms][4-bit ver=7][12-bit rand_a (seq counter)][2-bit var=0b10][62-bit rand_b]

    Bir xil millisekund ichida rand_a sekvensiya-counter sifatida o'sadi.
    Counter to'lib ketsa (>4095), timestamp sun'iy oshiriladi (spin-wait yo'q).

    Returns:
        uuid.UUID: Yangi UUID v7 qiymati.
    """
    global _last_ts_ms, _counter

    with _lock:
        ts_ms = int(time.time() * 1000) & 0xFFFFFFFFFFFF

        if ts_ms == _last_ts_ms:
            _counter += 1
            if _counter > _COUNTER_MAX:
                # Counter to'ldi — keyingi logical millisekund ga o'tish
                _last_ts_ms += 1
                ts_ms = _last_ts_ms
                _counter = 0
        elif ts_ms > _last_ts_ms:
            _last_ts_ms = ts_ms
            _counter = 0
        else:
            # Tizim soati orqaga ketdi (NTP tuzatish) — monotonlikni saqlaymiz
            _last_ts_ms += 1
            ts_ms = _last_ts_ms
            _counter = 0

        seq = _counter

    # 8 bayt tasodifiy (rand_b: 62 bit)
    rand_b = int.from_bytes(os.urandom(8), "big") & 0x3FFFFFFFFFFFFFFF

    # [48-bit ts_ms] | [4-bit ver=7] | [12-bit seq (rand_a)]
    high = (ts_ms << 16) | (0x7 << 12) | (seq & 0xFFF)

    # [2-bit var=0b10] | [62-bit rand_b]
    low = (0b10 << 62) | rand_b

    return uuid.UUID(int=(high << 64) | low)


def uuid7_str() -> str:
    """UUID v7 ni string formatida qaytarish."""
    return str(uuid7())
