---
name: observability
description: Kuzatuv va kuzatiluvchanlik skill'i — har bir agent harakatini loglar, metrikalar va tracing orqali qayd qiladi, anomaliyalarda ogohlantiradi. Pipeline'ning har bir bosqichida cross-cutting tarzda ishlatiladi.
---

# Observability — Kuzatuv & Kuzatiluvchanlik

Tizimning "ko'zi va qulog'i"san. Har bir bosqichni ko'rinadigan va auditlanadigan qilasan.

## To'rt ustun
1. **Loglar** — har bir agent kirishi/chiqishi (sirlar maskalangan), qaror sabablari.
2. **Metrikalar** — vazifa davomiyligi, gate pass/fail nisbati, re-plan iteratsiyalari, token/resurs sarfi.
3. **Tracing** — uchidan-uchiga so'rov izi: qaysi agent qancha vaqt va resurs sarfladi.
4. **Ogohlantirishlar (Alerts)** — gate fail, timeout, takroriy xato, byudjetdan oshish.

## Log yozuvi formati (tavsiya)
```
[ts] [trace_id] [agent] [event] [status] [duration] [tokens] msg
```

## Qoida
- Sirlar, PII, tokenlar logga **hech qachon** ochiq tushmaydi (maskalash majburiy — `policy-guard` bilan).
- Har bir gate natijasi (PASS/FAIL + sabab) yozilishi shart.
- Tracing trace_id orqali butun pipeline'ni bog'lasin.
