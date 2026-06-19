"""
Push provider abstraktsiyasi — T19 Push Worker.

PushProvider — abstrakt async interfeys:
  send(device_token, title, body, data) -> PushResult

Implementatsiyalar:
  FcmProvider  — FCM HTTP v1 (OAuth2 Bearer) yoki legacy server-key.
  ApnsProvider — APNs token-based (JWT ES256, HTTP/2 httpx).
  FakePushProvider — test uchun (yuborilganlarni ro'yxatga oladi).

get_push_provider() — factory (config asosida, platform bo'yicha).

XAVFSIZLIK:
  FCM/APNs kalitlari faqat config/env orqali — bu faylda hech qanday kalit yo'q.
  Haqiqiy kredensiallar .env.prod da beriladi.

NO-OP QOIDASI (telemetry.py naqshi):
  Kredensial/config yo'q bo'lsa — logger.warning + PushResult(ok=False) qaytaradi.
  ISTISNO TASHLAMAYDI — ilovani buzmaydigan, qo'shimcha konfiguratsiyasiz ishlaydi.
  ImportError ham ushlanadi (ixtiyoriy bog'liqlik).

FCM LEGACY ESLATMASI:
  FCM_SERVER_KEY (legacy HTTP v0) eskirgan — Google 2024-yildan o'chirishni e'lon qildi.
  Yangi va mavjud loyihalar uchun FCM HTTP v1 + service-account JSON ishlatilsin.
  Bu fayl legacy key'ni qo'llaydi (eski deployment uchun), lekin
  FCM_PROJECT_ID + FCM_CREDENTIALS_FILE/FCM_CREDENTIALS (v1) afzalroq.

TOKEN INVALIDATSIYA:
  PushResult.invalid_token=True → service.py device_token ni deaktiv qiladi.
  FCM: 404 UNREGISTERED yoki NOT_FOUND.
  APNs: 410 yoki BadDeviceToken / Unregistered.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ─── Natija dataclass ─────────────────────────────────────────────────────────


@dataclass
class PushResult:
    """
    Push yuborish natijasi.

    ok           — True: muvaffaqiyatli; False: xato (retry yoki skip).
    invalid_token— True: token eskirgan/noto'g'ri → device_token ni deaktiv qilish kerak.
    error        — xato tavsifi (log uchun, PII bo'lmasin).
    """

    ok: bool
    invalid_token: bool = False
    error: str | None = None


# ─── Abstrakt interfeys ───────────────────────────────────────────────────────


class PushProvider(ABC):
    """Push bildirishnoma yuboruvchi abstrakt async interfeys."""

    @abstractmethod
    async def send(
        self,
        device_token: str,
        title: str,
        body: str,
        data: dict[str, Any] | None = None,
    ) -> PushResult:
        """
        Push bildirishnoma yuboradi.

        Args:
            device_token: Qurilma token (FCM registration token yoki APNs device token).
            title:        Bildirishnoma sarlavhasi.
            body:         Bildirishnoma matni.
            data:         Qo'shimcha ma'lumotlar (ixtiyoriy).

        Returns:
            PushResult(ok, invalid_token, error).
        """
        ...


# ─── FCM Provider ─────────────────────────────────────────────────────────────


class FcmProvider(PushProvider):
    """
    FCM (Firebase Cloud Messaging) push provider.

    FCM HTTP v1 (tavsiya): OAuth2 Bearer token + service-account.
    FCM legacy (eskirgan): Authorization: key=<server_key> sarlavhasi.

    ESKIRGAN ESLATMA:
      FCM_SERVER_KEY (legacy) — Google 2024-yildan FCM legacy API ni o'chirishni
      e'lon qildi. Faqat eski deployment uchun saqlangan. Yangi loyihalar uchun
      FCM HTTP v1 + FCM_PROJECT_ID + FCM_CREDENTIALS_FILE ishlatilsin.

    Token invalidatsiya:
      404 yoki error_code UNREGISTERED/NOT_FOUND → PushResult(invalid_token=True).

    No-op:
      Hech qanday kredensial yo'q → warning log + PushResult(ok=False).
    """

    # FCM v1 endpoint: https://fcm.googleapis.com/v1/projects/{project_id}/messages:send
    _FCM_V1_URL = "https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"

    # FCM legacy endpoint (eskirgan — DEPRECATED)
    _FCM_LEGACY_URL = "https://fcm.googleapis.com/fcm/send"

    def __init__(
        self,
        project_id: str | None = None,
        credentials_file: str | None = None,
        credentials_json: str | None = None,
        server_key: str | None = None,
    ) -> None:
        """
        Args:
            project_id:       Firebase proyekt ID (v1 uchun).
            credentials_file: Service-account JSON fayl yo'li (v1 uchun).
            credentials_json: Service-account JSON satr/base64 (v1 uchun).
            server_key:       Legacy FCM server key (eskirgan, v0 uchun).
        """
        self._project_id = project_id
        self._credentials_file = credentials_file
        self._credentials_json = credentials_json
        self._server_key = server_key

        # Rejim aniqlanishi
        self._mode: str  # "v1_service_account" | "v1_no_oauth" | "legacy" | "noop"
        if project_id and (credentials_file or credentials_json):
            self._mode = "v1_service_account"
        elif server_key:
            # ESKIRGAN: legacy server key
            logger.warning(
                "FcmProvider: FCM_SERVER_KEY (legacy) ishlatilmoqda. "
                "Bu API eskirgan — Google 2024-yildan o'chirishni e'lon qildi. "
                "FCM HTTP v1 + FCM_PROJECT_ID + FCM_CREDENTIALS_FILE ga o'ting."
            )
            self._mode = "legacy"
        else:
            logger.warning(
                "FcmProvider: FCM kredensial/config topilmadi. "
                "FCM push yuborilmaydi (no-op). "
                "Production da FCM_PROJECT_ID + FCM_CREDENTIALS_FILE (.env.prod) bering."
            )
            self._mode = "noop"

    async def _get_oauth2_token(self) -> str | None:
        """
        FCM v1 uchun OAuth2 Bearer token oladi.

        google-auth yoki cryptography + jwt orqali service-account JWT imzolaydi.
        Agar google-auth mavjud bo'lmasa — jwt + cryptography bilan qo'lda imzolaydi.

        Returns:
            Bearer token satri yoki None (xato bo'lsa).
        """
        import json as json_mod

        # Service-account JSON yuklash
        sa_data: dict[str, Any] | None = None

        if self._credentials_file:
            try:
                with open(self._credentials_file, encoding="utf-8") as f:
                    sa_data = json_mod.load(f)
            except (OSError, ValueError) as exc:
                logger.error(
                    "FcmProvider: credentials_file o'qib bo'lmadi: %s", exc
                )
                return None

        elif self._credentials_json:
            try:
                import base64

                # Base64 yoki to'g'ridan-to'g'ri JSON
                raw = self._credentials_json.strip()
                try:
                    decoded = base64.b64decode(raw).decode("utf-8")
                    sa_data = json_mod.loads(decoded)
                except Exception:
                    sa_data = json_mod.loads(raw)
            except (ValueError, Exception) as exc:
                logger.error(
                    "FcmProvider: credentials_json parse xatosi: %s", exc
                )
                return None

        if not sa_data:
            return None

        # OAuth2 scope
        scope = "https://www.googleapis.com/auth/firebase.messaging"

        # google-auth mavjud bo'lsa — ishlatish
        try:
            from google.oauth2 import service_account  # type: ignore[import]
            import google.auth.transport.requests  # type: ignore[import]

            credentials = service_account.Credentials.from_service_account_info(
                sa_data, scopes=[scope]
            )
            request = google.auth.transport.requests.Request()
            credentials.refresh(request)
            return credentials.token
        except ImportError:
            pass  # google-auth yo'q — qo'lda JWT
        except Exception as exc:
            logger.error("FcmProvider: google-auth token xatosi: %s", exc)
            return None

        # Qo'lda JWT (PyJWT + cryptography) — google-auth o'rniga
        try:
            import jwt as pyjwt

            private_key_pem = sa_data.get("private_key", "")
            client_email = sa_data.get("client_email", "")
            token_uri = sa_data.get("token_uri", "https://oauth2.googleapis.com/token")

            if not private_key_pem or not client_email:
                logger.error(
                    "FcmProvider: service-account da private_key/client_email yo'q"
                )
                return None

            now = int(time.time())
            payload = {
                "iss": client_email,
                "sub": client_email,
                "aud": token_uri,
                "iat": now,
                "exp": now + 3600,
                "scope": scope,
            }
            signed_jwt = pyjwt.encode(payload, private_key_pem, algorithm="RS256")

            # Token endpoint ga POST
            import httpx

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    token_uri,
                    data={
                        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                        "assertion": signed_jwt,
                    },
                )

            if resp.status_code == 200:
                return resp.json().get("access_token")
            else:
                logger.error(
                    "FcmProvider: OAuth2 token endpoint xatosi: %d %s",
                    resp.status_code,
                    resp.text[:200],
                )
                return None

        except ImportError as exc:
            logger.error(
                "FcmProvider: jwt/httpx paketi topilmadi: %s. "
                "pip install PyJWT httpx",
                exc,
            )
            return None
        except Exception as exc:
            logger.error("FcmProvider: JWT imzolash xatosi: %s", exc)
            return None

    async def send(
        self,
        device_token: str,
        title: str,
        body: str,
        data: dict[str, Any] | None = None,
    ) -> PushResult:
        """FCM orqali push yuboradi."""
        if self._mode == "noop":
            return PushResult(ok=False, error="fcm_not_configured")

        # Token maskalash (PII log ga tushmaydi)
        masked = device_token[:8] + "***" if len(device_token) > 8 else "***"

        if self._mode == "legacy":
            return await self._send_legacy(device_token, masked, title, body, data)
        else:
            return await self._send_v1(device_token, masked, title, body, data)

    async def _send_v1(
        self,
        device_token: str,
        masked_token: str,
        title: str,
        body: str,
        data: dict[str, Any] | None,
    ) -> PushResult:
        """FCM HTTP v1 orqali yuborish."""
        import httpx

        oauth_token = await self._get_oauth2_token()
        if not oauth_token:
            logger.error(
                "FcmProvider v1: OAuth2 token olib bo'lmadi. token=%.10s***",
                masked_token,
            )
            return PushResult(ok=False, error="fcm_oauth2_token_failed")

        url = self._FCM_V1_URL.format(project_id=self._project_id)
        message: dict[str, Any] = {
            "token": device_token,
            "notification": {"title": title, "body": body},
        }
        if data:
            # FCM data maydonlari faqat satr bo'lishi kerak
            message["data"] = {k: str(v) for k, v in data.items()}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    url,
                    json={"message": message},
                    headers={
                        "Authorization": f"Bearer {oauth_token}",
                        "Content-Type": "application/json",
                    },
                )
        except Exception as exc:
            logger.error(
                "FcmProvider v1: tarmoq xatosi: %s token=%.10s***", exc, masked_token
            )
            return PushResult(ok=False, error=f"fcm_network_error: {exc!s:.100}")

        return self._parse_v1_response(resp, masked_token)

    def _parse_v1_response(
        self,
        resp: Any,
        masked_token: str,
    ) -> PushResult:
        """FCM HTTP v1 javobini tahlil qiladi."""
        if resp.status_code == 200:
            logger.debug(
                "FcmProvider v1: muvaffaqiyatli. token=%.10s***", masked_token
            )
            return PushResult(ok=True)

        # Token eskirgan/noto'g'ri
        if resp.status_code == 404:
            try:
                body_json = resp.json()
                err_code = (
                    body_json.get("error", {})
                    .get("details", [{}])[0]
                    .get("errorCode", "")
                )
            except Exception:
                err_code = ""
            if err_code in ("UNREGISTERED", "NOT_FOUND") or resp.status_code == 404:
                logger.warning(
                    "FcmProvider v1: token eskirgan (UNREGISTERED). token=%.10s***",
                    masked_token,
                )
                return PushResult(ok=False, invalid_token=True, error="fcm_unregistered")

        # Boshqa xatolar
        logger.error(
            "FcmProvider v1: HTTP xato %d. token=%.10s***",
            resp.status_code,
            masked_token,
        )
        return PushResult(
            ok=False,
            error=f"fcm_http_{resp.status_code}: {resp.text[:200]}",
        )

    async def _send_legacy(
        self,
        device_token: str,
        masked_token: str,
        title: str,
        body: str,
        data: dict[str, Any] | None,
    ) -> PushResult:
        """
        FCM legacy HTTP API orqali yuborish (ESKIRGAN).

        DIQQAT: Bu endpoint Google tomonidan o'chirilmoqda.
        FCM HTTP v1 ga o'ting: FCM_PROJECT_ID + FCM_CREDENTIALS_FILE.
        """
        import httpx

        payload: dict[str, Any] = {
            "to": device_token,
            "notification": {"title": title, "body": body},
        }
        if data:
            payload["data"] = data

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    self._FCM_LEGACY_URL,
                    json=payload,
                    headers={
                        "Authorization": f"key={self._server_key}",
                        "Content-Type": "application/json",
                    },
                )
        except Exception as exc:
            logger.error(
                "FcmProvider legacy: tarmoq xatosi: %s token=%.10s***",
                exc,
                masked_token,
            )
            return PushResult(ok=False, error=f"fcm_legacy_network: {exc!s:.100}")

        if resp.status_code == 200:
            try:
                rj = resp.json()
                # Legacy API: {"multicast_id":..., "success":1, "failure":0, "results":[...]}
                results = rj.get("results", [{}])
                first = results[0] if results else {}
                if "error" in first:
                    err = first["error"]
                    if err in ("NotRegistered", "InvalidRegistration"):
                        logger.warning(
                            "FcmProvider legacy: token eskirgan (%s). token=%.10s***",
                            err,
                            masked_token,
                        )
                        return PushResult(
                            ok=False, invalid_token=True, error=f"fcm_legacy_{err}"
                        )
                    logger.error(
                        "FcmProvider legacy: FCM xato=%s. token=%.10s***",
                        err,
                        masked_token,
                    )
                    return PushResult(ok=False, error=f"fcm_legacy_error:{err}")
                logger.debug(
                    "FcmProvider legacy: muvaffaqiyatli. token=%.10s***", masked_token
                )
                return PushResult(ok=True)
            except Exception as exc:
                logger.error(
                    "FcmProvider legacy: javob parse xatosi: %s", exc
                )
                return PushResult(ok=False, error=f"fcm_legacy_parse: {exc!s:.100}")

        if resp.status_code == 401:
            logger.error(
                "FcmProvider legacy: autentifikatsiya xatosi (401). "
                "FCM_SERVER_KEY noto'g'ri."
            )
            return PushResult(ok=False, error="fcm_legacy_unauthorized")

        logger.error(
            "FcmProvider legacy: HTTP xato %d. token=%.10s***",
            resp.status_code,
            masked_token,
        )
        return PushResult(
            ok=False,
            error=f"fcm_legacy_http_{resp.status_code}: {resp.text[:200]}",
        )


# ─── APNs Provider ────────────────────────────────────────────────────────────


class ApnsProvider(PushProvider):
    """
    APNs (Apple Push Notification service) push provider.

    Token-based autentifikatsiya: JWT ES256 (APNS_KEY_ID + APNS_TEAM_ID + .p8).
    httpx HTTP/2 yoki HTTP/1.1 orqali APNs endpoint ga POST.

    APNs endpoint:
      Production: https://api.push.apple.com/3/device/{token}
      Sandbox:    https://api.sandbox.push.apple.com/3/device/{token}

    JWT muddati: 60 daqiqa (apple talabi: 20-60 daqiqa). Kesh bilan.

    Token invalidatsiya:
      410 yoki {"reason": "BadDeviceToken"/"Unregistered"} → invalid_token=True.

    No-op:
      .p8 kalit yo'q (apns_key_file/apns_private_key_pem) → warning + no-op.
    """

    _APNS_PROD_URL = "https://api.push.apple.com/3/device/{token}"
    _APNS_SANDBOX_URL = "https://api.sandbox.push.apple.com/3/device/{token}"

    # JWT muddati (Apple: 20-60 daqiqa oralig'ida yangilash)
    _JWT_LIFETIME_SECS = 45 * 60  # 45 daqiqa

    def __init__(
        self,
        key_id: str | None = None,
        team_id: str | None = None,
        bundle_id: str | None = None,
        private_key_pem: str | None = None,
        key_file: str | None = None,
        use_sandbox: bool = False,
    ) -> None:
        self._key_id = key_id
        self._team_id = team_id
        self._bundle_id = bundle_id
        self._use_sandbox = use_sandbox

        # Private key PEM yuklash
        self._private_key_pem: str | None = private_key_pem

        if not private_key_pem and key_file:
            try:
                with open(key_file, encoding="utf-8") as f:
                    self._private_key_pem = f.read()
            except OSError as exc:
                logger.error(
                    "ApnsProvider: .p8 kalit fayli o'qib bo'lmadi (%s): %s",
                    key_file,
                    exc,
                )
                self._private_key_pem = None

        # No-op tekshiruvi
        self._configured = bool(
            self._key_id
            and self._team_id
            and self._bundle_id
            and self._private_key_pem
        )
        if not self._configured:
            logger.warning(
                "ApnsProvider: APNs kalitlari to'liq emas (key_id/team_id/bundle_id/key). "
                "APNs push yuborilmaydi (no-op). "
                "Production da APNS_KEY_FILE, APNS_KEY_ID, APNS_TEAM_ID, "
                "APNS_BUNDLE_ID (.env.prod) bering."
            )

        # JWT kesh
        self._cached_jwt: str | None = None
        self._jwt_issued_at: float = 0.0

    def _make_jwt(self) -> str | None:
        """
        APNs uchun ES256 JWT yaratadi (kesh bilan).

        Returns:
            JWT satr yoki None (xato bo'lsa).
        """
        now = time.time()
        # Kesh hali amal qilsa — qaytaramiz (10 daqiqa zaxira bilan)
        if (
            self._cached_jwt
            and (now - self._jwt_issued_at) < (self._JWT_LIFETIME_SECS - 600)
        ):
            return self._cached_jwt

        try:
            import jwt as pyjwt

            payload = {
                "iss": self._team_id,
                "iat": int(now),
            }
            headers = {
                "alg": "ES256",
                "kid": self._key_id,
            }
            token = pyjwt.encode(
                payload,
                self._private_key_pem,
                algorithm="ES256",
                headers=headers,
            )
            self._cached_jwt = token
            self._jwt_issued_at = now
            return token
        except ImportError as exc:
            logger.error(
                "ApnsProvider: PyJWT paketi topilmadi: %s. pip install PyJWT", exc
            )
            return None
        except Exception as exc:
            logger.error("ApnsProvider: JWT yaratish xatosi: %s", exc)
            return None

    async def send(
        self,
        device_token: str,
        title: str,
        body: str,
        data: dict[str, Any] | None = None,
    ) -> PushResult:
        """APNs orqali push yuboradi."""
        if not self._configured:
            return PushResult(ok=False, error="apns_not_configured")

        jwt_token = self._make_jwt()
        if not jwt_token:
            return PushResult(ok=False, error="apns_jwt_failed")

        masked = device_token[:8] + "***" if len(device_token) > 8 else "***"

        base_url = self._APNS_SANDBOX_URL if self._use_sandbox else self._APNS_PROD_URL
        url = base_url.format(token=device_token)

        aps_payload: dict[str, Any] = {
            "aps": {
                "alert": {"title": title, "body": body},
                "sound": "default",
            }
        }
        if data:
            aps_payload.update(data)

        import httpx

        try:
            # APNs HTTP/2 ni MAJBURIY talab qiladi — HTTP/1.1 ni RAD ETADI.
            # http2=True uchun `h2` paketi kerak (pyproject: httpx[http2]).
            async with httpx.AsyncClient(timeout=10.0, http2=True) as client:
                resp = await client.post(
                    url,
                    json=aps_payload,
                    headers={
                        "authorization": f"bearer {jwt_token}",
                        "apns-topic": self._bundle_id or "",
                        "apns-push-type": "alert",
                        "content-type": "application/json",
                    },
                )
        except Exception as exc:
            logger.error(
                "ApnsProvider: tarmoq xatosi: %s token=%.10s***", exc, masked
            )
            return PushResult(ok=False, error=f"apns_network_error: {exc!s:.100}")

        return self._parse_apns_response(resp, masked)

    def _parse_apns_response(self, resp: Any, masked_token: str) -> PushResult:
        """APNs javobini tahlil qiladi."""
        if resp.status_code == 200:
            logger.debug(
                "ApnsProvider: muvaffaqiyatli. token=%.10s***", masked_token
            )
            return PushResult(ok=True)

        # Token eskirgan/noto'g'ri
        if resp.status_code == 410:
            logger.warning(
                "ApnsProvider: token eskirgan (410). token=%.10s***", masked_token
            )
            return PushResult(ok=False, invalid_token=True, error="apns_gone_410")

        # Javob matnidan reason olish
        try:
            reason = resp.json().get("reason", "")
        except Exception:
            reason = ""

        if reason in ("BadDeviceToken", "Unregistered", "DeviceTokenNotForTopic"):
            logger.warning(
                "ApnsProvider: token noto'g'ri (%s). token=%.10s***",
                reason,
                masked_token,
            )
            return PushResult(
                ok=False, invalid_token=True, error=f"apns_{reason}"
            )

        logger.error(
            "ApnsProvider: HTTP xato %d reason=%r token=%.10s***",
            resp.status_code,
            reason,
            masked_token,
        )
        return PushResult(
            ok=False,
            error=f"apns_http_{resp.status_code}:{reason or resp.text[:100]}",
        )


# ─── Fake Provider (testlar uchun) ────────────────────────────────────────────


@dataclass
class _SentPush:
    """Yuborilgan push yozuvi — test introspeksiya uchun."""

    device_id: str
    channel: str
    title: str
    body: str
    data: dict[str, Any] = field(default_factory=dict)


class FakePushProvider(PushProvider):
    """
    Test uchun fake push provider.

    Haqiqiy tarmoq chaqiruvi yo'q — yuborilgan pushlarni xotirada saqlaydi.
    Test kodi `sent` ro'yxatini tekshiradi.

    fail_next:      True bo'lsa keyingi send() False qaytaradi (retry testi uchun).
    invalid_next:   True bo'lsa keyingi send() invalid_token=True qaytaradi.
    fail_count:     nechta ketma-ket send() muvaffaqiyatsiz bo'lishi lozim.
    """

    def __init__(self) -> None:
        self.sent: list[_SentPush] = []
        self._fail_next: int = 0
        self._invalid_next: int = 0

    def set_fail_next(self, n: int = 1) -> None:
        """Keyingi N ta send() uchun fail rejimi o'rnatadi."""
        self._fail_next = n

    def set_invalid_next(self, n: int = 1) -> None:
        """Keyingi N ta send() uchun invalid_token=True o'rnatadi."""
        self._invalid_next = n

    async def send(
        self,
        device_token: str,
        title: str,
        body: str,
        data: dict[str, Any] | None = None,
    ) -> PushResult:
        if self._invalid_next > 0:
            self._invalid_next -= 1
            logger.debug("FakePushProvider: send invalid_token (test)")
            return PushResult(ok=False, invalid_token=True, error="fake_invalid_token")

        if self._fail_next > 0:
            self._fail_next -= 1
            logger.debug("FakePushProvider: send muvaffaqiyatsiz (fail_next)")
            return PushResult(ok=False, error="fake_send_failed")

        self.sent.append(
            _SentPush(
                device_id=device_token,
                channel="fake",
                title=title,
                body=body,
                data=data or {},
            )
        )
        logger.debug(
            "FakePushProvider: push saqlandi token=%.10s*** title=%r",
            device_token,
            title,
        )
        return PushResult(ok=True)

    def reset(self) -> None:
        """Test izolyatsiyasi uchun holatni tozalaydi."""
        self.sent.clear()
        self._fail_next = 0
        self._invalid_next = 0


# ─── Factory ─────────────────────────────────────────────────────────────────


def get_push_provider() -> PushProvider:
    """
    Config asosida push provider qaytaradi.

    Platformga qarab yo'naltirish service.py da (_process_one_push ichida).
    Bu factory default provider (FCM) qaytaradi.

    APP_ENV == 'development' va FCM kredensial yo'q → FakePushProvider.
    Production: FcmProvider (config asosida).

    Dependency injection uchun ishlatiladi (worker on_startup da).
    """
    from app.core.config import settings

    has_fcm = bool(
        getattr(settings, "fcm_project_id", None)
        or getattr(settings, "fcm_credentials_file", None)
        or getattr(settings, "fcm_credentials", None)
        or getattr(settings, "fcm_server_key", None)
    )

    if settings.app_env == "development" and not has_fcm:
        logger.info("get_push_provider: FakePushProvider (development/no-fcm-config)")
        return FakePushProvider()

    return FcmProvider(
        project_id=getattr(settings, "fcm_project_id", None),
        credentials_file=getattr(settings, "fcm_credentials_file", None),
        credentials_json=getattr(settings, "fcm_credentials", None),
        server_key=getattr(settings, "fcm_server_key", None),
    )


def get_apns_provider() -> ApnsProvider:
    """APNs provider factory — config asosida."""
    from app.core.config import settings

    return ApnsProvider(
        key_id=getattr(settings, "apns_key_id", None),
        team_id=getattr(settings, "apns_team_id", None),
        bundle_id=getattr(settings, "apns_bundle_id", None),
        private_key_pem=getattr(settings, "apns_private_key_pem", None),
        key_file=getattr(settings, "apns_key_file", None),
        use_sandbox=bool(getattr(settings, "apns_use_sandbox", False)),
    )
