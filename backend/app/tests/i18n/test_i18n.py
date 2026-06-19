"""
i18n qatlami testlari — T3.

Infrasiz (aiosqlite + fakeredis) — haqiqiy PostgreSQL va Redis talab qilinmaydi.

Qamrab olingan scenariylar:
  - parse_accept_language: uz/ru/en/bo'sh/kompleks header
  - translate: kalit uz/ru, format params, noma'lum kalit fallback
  - HTTP: /auth/login noto'g'ri parol — Accept-Language bo'yicha til
  - HTTP: RBAC 403 — rbac.permission_denied, modul/action, til
  - HTTP: 422 validatsiya xatosi envelope formati
  - localized_name: name_uz/name_ru, fallback
  - current_locale ContextVar izolyatsiyasi
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import fakeredis.aioredis
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import get_db
from app.core.i18n import (
    DEFAULT_LOCALE,
    SUPPORTED_LOCALES,
    current_locale,
    localized_name,
    parse_accept_language,
)
from app.core.messages import translate
from app.core.jwt import hash_password
from app.core.redis import get_redis
from app.main import app
from app.models.base import Base
from app.models.user import AppUser


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
async def engine():
    """aiosqlite in-memory engine."""
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest.fixture
async def db_session(engine):
    """Har test uchun yangi async session."""
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def fake_redis():
    """fakeredis async klient."""
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield r
    await r.aclose()


@pytest.fixture
async def test_user(db_session: AsyncSession) -> AppUser:
    """Test foydalanuvchisi — administrator."""
    user = AppUser(
        id=uuid.uuid4(),
        full_name="Test User",
        phone="+998901112233",
        role="administrator",
        branch_id=None,
        password_hash=hash_password("TestPassword123!"),
        is_active=True,
        biometric_enrolled=False,
        locale="uz",
        device_id=None,
        version=1,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def i18n_client(db_session: AsyncSession, fake_redis):
    """Dependency override qilingan AsyncClient."""
    async def _get_test_db():
        yield db_session

    async def _get_test_redis():
        yield fake_redis

    app.dependency_overrides[get_db] = _get_test_db
    app.dependency_overrides[get_redis] = _get_test_redis

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client

    app.dependency_overrides.clear()


# ─── parse_accept_language testlari ──────────────────────────────────────────


def test_parse_accept_language_ru() -> None:
    """'ru' → 'ru'."""
    assert parse_accept_language("ru") == "ru"


def test_parse_accept_language_uz() -> None:
    """'uz' → 'uz'."""
    assert parse_accept_language("uz") == "uz"


def test_parse_accept_language_en_defaults() -> None:
    """'en' → DEFAULT_LOCALE ('uz') — qo'llab-quvvatlanmaydi."""
    assert parse_accept_language("en") == DEFAULT_LOCALE


def test_parse_accept_language_complex_ru() -> None:
    """'ru-RU,ru;q=0.9,en;q=0.8' → 'ru'."""
    assert parse_accept_language("ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7") == "ru"


def test_parse_accept_language_empty_string() -> None:
    """Bo'sh string → DEFAULT_LOCALE."""
    assert parse_accept_language("") == DEFAULT_LOCALE


def test_parse_accept_language_none() -> None:
    """None → DEFAULT_LOCALE."""
    assert parse_accept_language(None) == DEFAULT_LOCALE


def test_parse_accept_language_q_factor_priority() -> None:
    """'ru;q=0.5,uz;q=0.8' → 'uz' (uz q=0.8 > ru q=0.5)."""
    assert parse_accept_language("ru;q=0.5,uz;q=0.8") == "uz"


def test_parse_accept_language_unknown_only() -> None:
    """Faqat noma'lum til → DEFAULT_LOCALE."""
    assert parse_accept_language("fr,de;q=0.9") == DEFAULT_LOCALE


# ─── translate() testlari ─────────────────────────────────────────────────────


def test_translate_uz() -> None:
    """auth.invalid_credentials uz tilida."""
    result = translate("auth.invalid_credentials", locale="uz")
    assert "Telefon" in result or "parol" in result
    assert result == "Telefon yoki parol noto'g'ri"


def test_translate_ru() -> None:
    """auth.invalid_credentials ru tilida."""
    result = translate("auth.invalid_credentials", locale="ru")
    assert "Неверный" in result or "пароль" in result.lower() or "телефон" in result.lower()


def test_translate_inactive_user_uz() -> None:
    """auth.inactive_user uz tilida."""
    result = translate("auth.inactive_user", locale="uz")
    assert "bloklangan" in result.lower()


def test_translate_inactive_user_ru() -> None:
    """auth.inactive_user ru tilida."""
    result = translate("auth.inactive_user", locale="ru")
    assert "Аккаунт" in result or "заблокирован" in result


def test_translate_rbac_permission_denied_format_uz() -> None:
    """rbac.permission_denied uz tilida — {module}/{action}/{role} parametrlar."""
    result = translate(
        "rbac.permission_denied",
        locale="uz",
        module="catalog",
        action="delete",
        role="agent",
    )
    assert "catalog" in result
    assert "delete" in result
    assert "agent" in result


def test_translate_rbac_permission_denied_format_ru() -> None:
    """rbac.permission_denied ru tilida."""
    result = translate(
        "rbac.permission_denied",
        locale="ru",
        module="finance",
        action="approve",
        role="courier",
    )
    assert "finance" in result
    assert "approve" in result
    assert "courier" in result


def test_translate_unknown_key_fallback() -> None:
    """Noma'lum kalit → kalit o'zi qaytadi."""
    result = translate("nonexistent.key", locale="uz")
    assert result == "nonexistent.key"


def test_translate_uses_contextvar_when_locale_none() -> None:
    """locale=None → current_locale ContextVar ishlatiladi."""
    token = current_locale.set("ru")
    try:
        result = translate("auth.invalid_credentials")
        # ru tilida bo'lishi kerak
        assert "Неверный" in result or "пароль" in result.lower()
    finally:
        current_locale.reset(token)


def test_translate_validation_error_uz() -> None:
    """common.validation_error uz tilida."""
    result = translate("common.validation_error", locale="uz")
    assert "noto'g'ri" in result.lower() or "validatsiya" in result.lower() or "ma'lumot" in result.lower()


def test_translate_validation_error_ru() -> None:
    """common.validation_error ru tilida."""
    result = translate("common.validation_error", locale="ru")
    assert "некорректны" in result.lower() or "данные" in result.lower()


# ─── localized_name() testlari ───────────────────────────────────────────────


def test_localized_name_uz() -> None:
    """name_uz qaytadi."""
    obj = MagicMock()
    obj.name_uz = "Mahsulot"
    obj.name_ru = "Продукт"
    assert localized_name(obj, locale="uz") == "Mahsulot"


def test_localized_name_ru() -> None:
    """name_ru qaytadi."""
    obj = MagicMock()
    obj.name_uz = "Mahsulot"
    obj.name_ru = "Продукт"
    assert localized_name(obj, locale="ru") == "Продукт"


def test_localized_name_fallback_to_uz() -> None:
    """name_ru bo'sh bo'lsa uz ga fallback."""
    obj = MagicMock()
    obj.name_uz = "Mahsulot"
    obj.name_ru = None
    result = localized_name(obj, locale="ru")
    assert result == "Mahsulot"


def test_localized_name_uses_contextvar() -> None:
    """locale=None → current_locale ContextVar ishlatiladi."""
    obj = MagicMock()
    obj.name_uz = "Mahsulot"
    obj.name_ru = "Продукт"

    token = current_locale.set("ru")
    try:
        assert localized_name(obj) == "Продукт"
    finally:
        current_locale.reset(token)


def test_localized_name_empty_fallback() -> None:
    """name_uz ham yo'q → bo'sh string."""
    obj = MagicMock(spec=[])  # hech qanday atribyut yo'q
    result = localized_name(obj, locale="uz")
    assert result == ""


# ─── HTTP: /auth/login i18n testlari ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_login_wrong_password_ru_message(
    i18n_client: AsyncClient, test_user: AppUser
) -> None:
    """
    Noto'g'ri parol + Accept-Language: ru → 401, message ruscha,
    message_key=auth.invalid_credentials.
    """
    resp = await i18n_client.post(
        "/auth/login",
        json={"phone": test_user.phone, "password": "WrongPassword!"},
        headers={"Accept-Language": "ru"},
    )
    assert resp.status_code == 401
    data = resp.json()
    assert data["message_key"] == "auth.invalid_credentials"
    # Ruscha xabar
    assert "Неверный" in data["message"] or "пароль" in data["message"].lower()


@pytest.mark.asyncio
async def test_login_wrong_password_uz_message(
    i18n_client: AsyncClient, test_user: AppUser
) -> None:
    """
    Noto'g'ri parol + Accept-Language: uz → 401, message o'zbekcha,
    message_key=auth.invalid_credentials.
    """
    resp = await i18n_client.post(
        "/auth/login",
        json={"phone": test_user.phone, "password": "WrongPassword!"},
        headers={"Accept-Language": "uz"},
    )
    assert resp.status_code == 401
    data = resp.json()
    assert data["message_key"] == "auth.invalid_credentials"
    assert "Telefon" in data["message"] or "parol" in data["message"]


@pytest.mark.asyncio
async def test_login_inactive_user_ru_message(i18n_client: AsyncClient) -> None:
    """Bloklangan foydalanuvchi + Accept-Language: ru → 403, message ruscha."""
    # Bloklangan user yaratish
    from app.core.db import get_db as _get_db
    db = None
    async for s in app.dependency_overrides[_get_db]():
        db = s

    blocked = AppUser(
        id=uuid.uuid4(),
        full_name="Blocked",
        phone="+998909876543",
        role="agent",
        branch_id=None,
        password_hash=hash_password("TestPassword123!"),
        is_active=False,
        biometric_enrolled=False,
        locale="uz",
        device_id=None,
        version=1,
    )
    db.add(blocked)
    await db.flush()

    resp = await i18n_client.post(
        "/auth/login",
        json={"phone": blocked.phone, "password": "TestPassword123!"},
        headers={"Accept-Language": "ru"},
    )
    assert resp.status_code == 403
    data = resp.json()
    assert data["message_key"] == "auth.inactive_user"
    assert "заблокирован" in data["message"].lower() or "аккаунт" in data["message"].lower()


@pytest.mark.asyncio
async def test_login_success_no_envelope(
    i18n_client: AsyncClient, test_user: AppUser
) -> None:
    """Muvaffaqiyatli login — oddiy TokenPair javobi (envelope emas)."""
    resp = await i18n_client.post(
        "/auth/login",
        json={"phone": test_user.phone, "password": "TestPassword123!"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data


# ─── HTTP: 422 validatsiya xatosi envelope ───────────────────────────────────


@pytest.mark.asyncio
async def test_422_validation_error_envelope_uz(i18n_client: AsyncClient) -> None:
    """Bo'sh body → 422, envelope formatida, uz tilida."""
    resp = await i18n_client.post(
        "/auth/login",
        json={},
        headers={"Accept-Language": "uz"},
    )
    assert resp.status_code == 422
    data = resp.json()
    assert data["message_key"] == "common.validation_error"
    assert "message" in data
    assert "detail" in data
    assert isinstance(data["detail"], list)


@pytest.mark.asyncio
async def test_422_validation_error_envelope_ru(i18n_client: AsyncClient) -> None:
    """Bo'sh body + Accept-Language: ru → 422, message ruscha."""
    resp = await i18n_client.post(
        "/auth/login",
        json={},
        headers={"Accept-Language": "ru"},
    )
    assert resp.status_code == 422
    data = resp.json()
    assert data["message_key"] == "common.validation_error"
    # Ruscha xabar
    ru_msg = translate("common.validation_error", locale="ru")
    assert data["message"] == ru_msg


# ─── HTTP: RBAC 403 i18n testlari ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rbac_403_permission_denied_uz(
    i18n_client: AsyncClient, test_user: AppUser
) -> None:
    """
    require_permission → 403, message_key=rbac.permission_denied,
    modul/action ko'rinadi, Accept-Language: uz → o'zbekcha.
    """
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient as AC
    from app.core.db import get_db as _get_db
    from app.core.redis import get_redis as _get_redis
    from app.modules.rbac.dependency import require_permission
    from app.main import app as main_app

    # courier uchun user yaratish (finance:approve yo'q)
    db = None
    async for s in main_app.dependency_overrides[_get_db]():
        db = s

    courier = AppUser(
        id=uuid.uuid4(),
        full_name="Courier",
        phone="+998907654321",
        role="courier",
        branch_id=None,
        password_hash=hash_password("TestPassword123!"),
        is_active=True,
        biometric_enrolled=False,
        locale="uz",
        device_id=None,
        version=1,
    )
    db.add(courier)
    await db.flush()

    # Token olish
    login_resp = await i18n_client.post(
        "/auth/login",
        json={"phone": courier.phone, "password": "TestPassword123!"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]

    # Mini app yaratish
    mini_app = FastAPI()

    @mini_app.get("/protected")
    async def _protected(user=require_permission("finance", "approve")):
        return {"ok": True}

    # Exception handler qo'shish (main.py dagi kabi)
    from app.core.errors import AppError, error_envelope
    from app.core.messages import translate

    @mini_app.exception_handler(AppError)
    async def _app_error_handler(request, exc: AppError):
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=exc.status_code,
            content=error_envelope(exc.message_key, exc.localized_message(), exc.detail),
        )

    get_db_override = main_app.dependency_overrides.get(_get_db)
    get_redis_override = main_app.dependency_overrides.get(_get_redis)
    if get_db_override:
        mini_app.dependency_overrides[_get_db] = get_db_override
    if get_redis_override:
        mini_app.dependency_overrides[_get_redis] = get_redis_override

    async with AC(
        transport=ASGITransport(app=mini_app),
        base_url="http://testserver",
    ) as mini_client:
        resp = await mini_client.get(
            "/protected",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept-Language": "uz",
            },
        )

    assert resp.status_code == 403
    data = resp.json()
    assert data["message_key"] == "rbac.permission_denied"
    assert "finance" in data["message"]
    assert "approve" in data["message"]
    assert "courier" in data["message"]


@pytest.mark.asyncio
async def test_rbac_403_permission_denied_ru(
    i18n_client: AsyncClient, test_user: AppUser
) -> None:
    """
    require_permission → 403, Accept-Language: ru → ruscha xabar.
    """
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient as AC
    from app.core.db import get_db as _get_db
    from app.core.redis import get_redis as _get_redis
    from app.modules.rbac.dependency import require_permission
    from app.main import app as main_app

    db = None
    async for s in main_app.dependency_overrides[_get_db]():
        db = s

    agent = AppUser(
        id=uuid.uuid4(),
        full_name="Agent",
        phone="+998906543210",
        role="agent",
        branch_id=None,
        password_hash=hash_password("TestPassword123!"),
        is_active=True,
        biometric_enrolled=False,
        locale="uz",
        device_id=None,
        version=1,
    )
    db.add(agent)
    await db.flush()

    login_resp = await i18n_client.post(
        "/auth/login",
        json={"phone": agent.phone, "password": "TestPassword123!"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]

    mini_app = FastAPI()

    @mini_app.get("/protected-ru")
    async def _protected(user=require_permission("rbac", "delete")):
        return {"ok": True}

    from app.core.errors import AppError, error_envelope
    from app.core.i18n import parse_accept_language, current_locale

    @mini_app.exception_handler(AppError)
    async def _app_error_handler(request, exc: AppError):
        from fastapi.responses import JSONResponse
        # Til request'dan olish
        accept_lang = request.headers.get("Accept-Language")
        locale = parse_accept_language(accept_lang)
        return JSONResponse(
            status_code=exc.status_code,
            content=error_envelope(exc.message_key, exc.localized_message(locale), exc.detail),
        )

    get_db_override = main_app.dependency_overrides.get(_get_db)
    get_redis_override = main_app.dependency_overrides.get(_get_redis)
    if get_db_override:
        mini_app.dependency_overrides[_get_db] = get_db_override
    if get_redis_override:
        mini_app.dependency_overrides[_get_redis] = get_redis_override

    async with AC(
        transport=ASGITransport(app=mini_app),
        base_url="http://testserver",
    ) as mini_client:
        resp = await mini_client.get(
            "/protected-ru",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept-Language": "ru",
            },
        )

    assert resp.status_code == 403
    data = resp.json()
    assert data["message_key"] == "rbac.permission_denied"
    # Ruscha xabarda "Доступ запрещён" yoki "недоступно" bo'lishi kerak
    assert "запрещён" in data["message"] or "Доступ" in data["message"] or "недоступно" in data["message"]
    # Parametrlar joylashgan
    assert "rbac" in data["message"]
    assert "delete" in data["message"]


# ─── current_locale ContextVar izolyatsiyasi ─────────────────────────────────


def test_current_locale_default() -> None:
    """Default locale — 'uz'."""
    # Yangi ContextVar token bilan
    assert current_locale.get() == DEFAULT_LOCALE


def test_current_locale_set_reset() -> None:
    """set/reset to'g'ri ishlaydi."""
    assert current_locale.get() == DEFAULT_LOCALE
    token = current_locale.set("ru")
    assert current_locale.get() == "ru"
    current_locale.reset(token)
    assert current_locale.get() == DEFAULT_LOCALE


# ─── Envelope format testlari ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_error_envelope_has_all_fields(
    i18n_client: AsyncClient, test_user: AppUser
) -> None:
    """401 xato javobi message_key, message, detail maydonlarini o'z ichiga oladi."""
    resp = await i18n_client.post(
        "/auth/login",
        json={"phone": test_user.phone, "password": "WrongPassword!"},
    )
    assert resp.status_code == 401
    data = resp.json()
    assert "message_key" in data
    assert "message" in data
    assert "detail" in data


# ─── HIGH: 422 javobida xom parol echo qilinmasligi ─────────────────────────


@pytest.mark.asyncio
async def test_422_no_raw_password_in_response(i18n_client: AsyncClient) -> None:
    """
    HIGH (Security): Qisqa/noto'g'ri parol bilan login → 422,
    javob matnida parol qiymati ko'rinmasin.
    Envelope format bo'lsin (message_key bor).
    """
    short_password = "ab"
    resp = await i18n_client.post(
        "/auth/login",
        json={"phone": "+998901234567", "password": short_password},
    )
    assert resp.status_code == 422
    # Javob matnida parol qiymati bo'lmasin
    resp_text = resp.text
    assert short_password not in resp_text

    data = resp.json()
    # Envelope format
    assert data["message_key"] == "common.validation_error"
    assert "message" in data
    assert "detail" in data
    # detail list — har bir element 'input' maydoni bo'lmasin
    assert isinstance(data["detail"], list)
    for err in data["detail"]:
        assert "input" not in err, f"'input' maydoni javobda topildi: {err}"
        assert "url" not in err, f"'url' maydoni javobda topildi: {err}"
        assert "ctx" not in err, f"'ctx' maydoni javobda topildi: {err}"


@pytest.mark.asyncio
async def test_422_no_raw_token_in_response(i18n_client: AsyncClient) -> None:
    """
    HIGH (Security): Noto'g'ri format refresh_token → 422,
    token qiymati javobda echo qilinmasin.
    """
    fake_token = "my-secret-token-value"
    resp = await i18n_client.post(
        "/auth/refresh",
        json={"refresh_token": fake_token},
    )
    # 422 yoki 401 — ikkala holda ham token qiymati ko'rinmasin
    assert resp.status_code in (422, 401)
    assert fake_token not in resp.text


# ─── MEDIUM (SRE): HTTPException 404 → envelope format ──────────────────────


@pytest.mark.asyncio
async def test_404_returns_envelope(i18n_client: AsyncClient) -> None:
    """
    MEDIUM (SRE): Mavjud bo'lmagan endpoint → 404,
    javob envelope formatida, message_key=common.not_found.
    """
    resp = await i18n_client.get("/nonexistent-endpoint-xyz")
    assert resp.status_code == 404
    data = resp.json()
    assert data["message_key"] == "common.not_found"
    assert "message" in data
    assert "detail" in data


@pytest.mark.asyncio
async def test_404_message_uz(i18n_client: AsyncClient) -> None:
    """404 → common.not_found uz tilida."""
    resp = await i18n_client.get(
        "/nonexistent-endpoint-xyz",
        headers={"Accept-Language": "uz"},
    )
    assert resp.status_code == 404
    data = resp.json()
    expected = translate("common.not_found", locale="uz")
    assert data["message"] == expected


@pytest.mark.asyncio
async def test_404_message_ru(i18n_client: AsyncClient) -> None:
    """404 → common.not_found ru tilida."""
    resp = await i18n_client.get(
        "/nonexistent-endpoint-xyz",
        headers={"Accept-Language": "ru"},
    )
    assert resp.status_code == 404
    data = resp.json()
    expected = translate("common.not_found", locale="ru")
    assert data["message"] == expected


# ─── MEDIUM (SRE): 500 handler — trace chiqmasin ─────────────────────────────


@pytest.mark.asyncio
async def test_500_handler_no_trace(i18n_client: AsyncClient) -> None:
    """
    MEDIUM (SRE): unhandled_exception_handler to'g'ri envelope qaytarishini tekshiradi.

    main.py dagi handler ni to'g'ridan-to'g'ri sinash: handler RuntimeError qabul qilsa
    envelope + common.internal_error qaytaradi, trace chiqmaydi.
    """
    from unittest.mock import AsyncMock
    from fastapi import Request
    from fastapi.responses import JSONResponse
    from app.main import unhandled_exception_handler
    from app.core.errors import error_envelope
    from app.core.messages import translate as _translate

    # Mock request
    mock_request = AsyncMock(spec=Request)
    exc = RuntimeError("SECRET internal traceback info")

    response: JSONResponse = await unhandled_exception_handler(mock_request, exc)

    assert response.status_code == 500
    import json
    data = json.loads(response.body)
    assert data["message_key"] == "common.internal_error"
    assert "message" in data
    assert data["detail"] is None
    # Ichki xato matni javobda ko'rinmasin
    body_str = response.body.decode()
    assert "SECRET" not in body_str
    assert "traceback" not in body_str.lower()
    assert "RuntimeError" not in body_str


# ─── MEDIUM (Security): parse_accept_language uzun header DoS ────────────────


def test_parse_accept_language_long_header_returns_default() -> None:
    """
    MEDIUM (Security): 256 belgidan uzun Accept-Language header →
    DEFAULT_LOCALE qaytadi (DoS oldini olish).
    """
    long_header = "ru," + "a" * 300
    assert len(long_header) > 256
    result = parse_accept_language(long_header)
    assert result == DEFAULT_LOCALE


def test_parse_accept_language_exactly_256_chars() -> None:
    """256 belgilik header — normal ishlaydi (chegarada)."""
    header = "uz" + "," * 254  # 256 belgi, faqat 'uz' lang tag bor
    assert len(header) == 256
    result = parse_accept_language(header)
    # 256 belgi — normal, DEFAULT yoki uz
    assert result in (DEFAULT_LOCALE, "uz")


def test_parse_accept_language_257_chars_returns_default() -> None:
    """257 belgilik header → DEFAULT_LOCALE."""
    header = "ru" + "x" * 255  # 257 belgi
    assert len(header) == 257
    result = parse_accept_language(header)
    assert result == DEFAULT_LOCALE


# ─── Middleware: ?lang= query ustunligi ──────────────────────────────────────


@pytest.mark.asyncio
async def test_lang_query_param_ru(i18n_client: AsyncClient, test_user: AppUser) -> None:
    """
    ?lang=ru query parametri Accept-Language headerdan ustun turadi.
    Noto'g'ri parol → 401, message ruscha bo'lishi kerak.
    """
    resp = await i18n_client.post(
        "/auth/login?lang=ru",
        json={"phone": test_user.phone, "password": "WrongPass!"},
        headers={"Accept-Language": "uz"},  # query param ustun
    )
    assert resp.status_code == 401
    data = resp.json()
    assert data["message_key"] == "auth.invalid_credentials"
    assert "Неверный" in data["message"] or "пароль" in data["message"].lower()


@pytest.mark.asyncio
async def test_lang_query_param_uz_overrides_ru_header(
    i18n_client: AsyncClient, test_user: AppUser
) -> None:
    """
    ?lang=uz + Accept-Language: ru → o'zbekcha javob (query param ustun).
    """
    resp = await i18n_client.post(
        "/auth/login?lang=uz",
        json={"phone": test_user.phone, "password": "WrongPass!"},
        headers={"Accept-Language": "ru"},
    )
    assert resp.status_code == 401
    data = resp.json()
    assert data["message_key"] == "auth.invalid_credentials"
    assert "Telefon" in data["message"] or "parol" in data["message"]


# ─── translate: barcha muhim kalitlar uz/ru bor ──────────────────────────────


@pytest.mark.parametrize("key", [
    "auth.token_expired",
    "auth.token_invalid",
    "auth.token_wrong_type",
    "common.not_found",
    "common.internal_error",
])
def test_translate_key_exists_uz(key: str) -> None:
    """Har kalit uz tilida mavjud va key o'zi qaytmaydi."""
    result = translate(key, locale="uz")
    assert result != key, f"Key '{key}' uz tilida tarjima topilmadi"
    assert len(result) > 0


@pytest.mark.parametrize("key", [
    "auth.token_expired",
    "auth.token_invalid",
    "auth.token_wrong_type",
    "common.not_found",
    "common.internal_error",
])
def test_translate_key_exists_ru(key: str) -> None:
    """Har kalit ru tilida mavjud va key o'zi qaytmaydi."""
    result = translate(key, locale="ru")
    assert result != key, f"Key '{key}' ru tilida tarjima topilmadi"
    assert len(result) > 0
