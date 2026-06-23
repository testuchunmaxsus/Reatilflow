"""
Xabarlar katalogi — barcha lokalizatsiyalangan xabarlar shu yerda.

Format: MESSAGES[message_key][locale] = "matn shablon"

Shablon parametrlari {param} bilan belgilanadi.
`translate()` funksiyasi shu katalogdan foydalanadi.

Qo'shilgan kalitlar:
  auth.*         — autentifikatsiya xatolari
  rbac.*         — ruxsat xatolari
  common.*       — umumiy xatolar (not_found, validation, internal)
"""

from __future__ import annotations

import logging

_logger = logging.getLogger(__name__)

# ─── Xabarlar katalogi ───────────────────────────────────────────────────────

MESSAGES: dict[str, dict[str, str]] = {
    # ── Autentifikatsiya ─────────────────────────────────────────────────────
    "auth.invalid_credentials": {
        "uz": "Telefon yoki parol noto'g'ri",
        "ru": "Неверный номер телефона или пароль",
    },
    "auth.inactive_user": {
        "uz": "Hisob bloklangan",
        "ru": "Аккаунт заблокирован",
    },
    "auth.token_expired": {
        "uz": "Token muddati tugagan",
        "ru": "Срок действия токена истёк",
    },
    "auth.token_invalid": {
        "uz": "Token yaroqsiz",
        "ru": "Токен недействителен",
    },
    "auth.token_wrong_type": {
        "uz": "Token turi noto'g'ri",
        "ru": "Неверный тип токена",
    },
    "auth.authentication_required": {
        "uz": "Autentifikatsiya talab qilinadi",
        "ru": "Требуется аутентификация",
    },
    "auth.user_not_found": {
        "uz": "Foydalanuvchi topilmadi",
        "ru": "Пользователь не найден",
    },

    # ── RBAC ────────────────────────────────────────────────────────────────
    "rbac.permission_denied": {
        "uz": "Ruxsat yo'q: '{module}' modulida '{action}' amali '{role}' roli uchun taqiqlangan",
        "ru": "Доступ запрещён: действие '{action}' в модуле '{module}' недоступно для роли '{role}'",
    },

    # ── Enterprise / Module gating (MT3) ─────────────────────────────────────
    "enterprise.module_disabled": {
        "uz": "'{module}' moduli bu korxonada yoqilmagan",
        "ru": "Модуль '{module}' не включён для данного предприятия",
    },
    "enterprise.suspended": {
        "uz": "Korxona faoliyati to'xtatilgan. Administrator bilan bog'laning",
        "ru": "Деятельность предприятия приостановлена. Обратитесь к администратору",
    },

    # ── Superadmin (MT4) ──────────────────────────────────────────────────────
    "superadmin.forbidden": {
        "uz": "Bu amal faqat superadmin uchun",
        "ru": "Это действие доступно только суперадминистратору",
    },
    "superadmin.enterprise_not_found": {
        "uz": "Korxona topilmadi",
        "ru": "Предприятие не найдено",
    },
    "superadmin.version_conflict": {
        "uz": "Versiya konflikti: boshqa foydalanuvchi korxonani o'zgartirgan",
        "ru": "Конфликт версий: другой пользователь изменил предприятие",
    },
    "superadmin.invalid_status": {
        "uz": "Noto'g'ri status: faqat 'active' yoki 'suspended' qabul qilinadi",
        "ru": "Неверный статус: допустимы только 'active' или 'suspended'",
    },

    # ── Katalog ─────────────────────────────────────────────────────────────
    "catalog.product_not_found": {
        "uz": "Mahsulot topilmadi",
        "ru": "Товар не найден",
    },
    "catalog.duplicate_sku": {
        "uz": "Bu SKU allaqachon mavjud",
        "ru": "Такой SKU уже существует",
    },
    "catalog.duplicate_barcode": {
        "uz": "Bu barcode allaqachon mavjud",
        "ru": "Такой штрихкод уже существует",
    },
    "catalog.category_not_found": {
        "uz": "Kategoriya topilmadi",
        "ru": "Категория не найдена",
    },
    "catalog.segment_not_found": {
        "uz": "Narx segmenti topilmadi",
        "ru": "Ценовой сегмент не найден",
    },
    "catalog.version_conflict": {
        "uz": "Versiya konflikti: boshqa foydalanuvchi mahsulotni o'zgartirgan",
        "ru": "Конфликт версий: другой пользователь изменил товар",
    },
    "catalog.invalid_photo": {
        "uz": "Rasm fayli noto'g'ri: faqat JPEG/PNG/WebP formatlari va 5MB gacha",
        "ru": "Некорректный файл изображения: только JPEG/PNG/WebP форматы и до 5MB",
    },
    "catalog.storage_error": {
        "uz": "Rasm saqlash xizmati hozircha mavjud emas, keyinroq urinib ko'ring",
        "ru": "Сервис хранения файлов временно недоступен, попробуйте позже",
    },

    # ── Customers (do'konlar) ────────────────────────────────────────────────
    "customers.store_not_found": {
        "uz": "Do'kon topilmadi",
        "ru": "Магазин не найден",
    },
    "customers.duplicate_inn": {
        "uz": "Bu INN allaqachon mavjud",
        "ru": "Такой ИНН уже существует",
    },
    "customers.agent_not_found": {
        "uz": "Agent topilmadi",
        "ru": "Агент не найден",
    },
    "customers.version_conflict": {
        "uz": "Versiya konflikti: boshqa foydalanuvchi do'konni o'zgartirgan",
        "ru": "Конфликт версий: другой пользователь изменил магазин",
    },
    "customers.forbidden_branch": {
        "uz": "Sizning filialingizdan tashqari do'kon",
        "ru": "Магазин вне вашего филиала",
    },
    "customers.forbidden": {
        "uz": "Bu amalni bajarish uchun administrator huquqi kerak",
        "ru": "Для выполнения этого действия требуются права администратора",
    },

    # ── Foydalanuvchilar (users) ─────────────────────────────────────────────
    "users.user_not_found": {
        "uz": "Foydalanuvchi topilmadi",
        "ru": "Пользователь не найден",
    },
    "users.duplicate_phone": {
        "uz": "Bu telefon raqam allaqachon ro'yxatdan o'tgan",
        "ru": "Данный номер телефона уже зарегистрирован",
    },
    "users.invalid_role": {
        "uz": "Noto'g'ri rol: faqat administrator, agent, courier, accountant, store rollari qabul qilinadi",
        "ru": "Недопустимая роль: допустимы только administrator, agent, courier, accountant, store",
    },
    "users.version_conflict": {
        "uz": "Versiya konflikti: boshqa foydalanuvchi ma'lumotlarni o'zgartirgan",
        "ru": "Конфликт версий: данные были изменены другим пользователем",
    },
    "users.cannot_deactivate_self": {
        "uz": "Administrator o'z hisobini deaktivatsiya qila olmaydi",
        "ru": "Администратор не может деактивировать собственный аккаунт",
    },

    # ── Ombor (stock) ────────────────────────────────────────────────────────
    "stock.product_not_found": {
        "uz": "Mahsulot topilmadi",
        "ru": "Товар не найден",
    },
    "stock.insufficient_quantity": {
        "uz": "Yetarli qoldiq yo'q: mavjud={available}, so'ralgan={requested}",
        "ru": "Недостаточный остаток: доступно={available}, запрошено={requested}",
    },
    "stock.version_conflict": {
        "uz": "Versiya konflikti: boshqa tranzaksiya qoldiqni o'zgartirgan",
        "ru": "Конфликт версий: другая транзакция изменила остаток",
    },

    # ── Buxgalteriya (finance) ────────────────────────────────────────────────
    "finance.store_not_found": {
        "uz": "Do'kon topilmadi",
        "ru": "Магазин не найден",
    },
    "finance.invalid_type": {
        "uz": "Noto'g'ri yozuv turi: faqat 'debit' yoki 'credit' qabul qilinadi",
        "ru": "Неверный тип записи: допустимы только 'debit' или 'credit'",
    },
    "finance.version_conflict": {
        "uz": "Versiya konflikti: boshqa tranzaksiya balansni o'zgartirgan",
        "ru": "Конфликт версий: другая транзакция изменила баланс",
    },
    "finance.currency_mismatch": {
        "uz": "Valyuta mos kelmadi: do'kon balansi '{existing}' valyutasida, yangi yozuv '{incoming}' valyutasida",
        "ru": "Несоответствие валюты: баланс магазина в валюте '{existing}', новая запись в валюте '{incoming}'",
    },

    # ── Buyurtma (orders) — T11 ──────────────────────────────────────────────
    "orders.order_not_found": {
        "uz": "Buyurtma topilmadi",
        "ru": "Заказ не найден",
    },
    "orders.invalid_transition": {
        "uz": "Noto'g'ri holat o'tishi: '{from_status}' dan '{to_status}' ga o'tish mumkin emas",
        "ru": "Недопустимый переход состояния: из '{from_status}' в '{to_status}' невозможен",
    },
    "orders.insufficient_stock": {
        "uz": "Yetarli qoldiq yo'q: mavjud={available}, so'ralgan={requested}",
        "ru": "Недостаточный остаток: доступно={available}, запрошено={requested}",
    },
    "orders.empty_lines": {
        "uz": "Buyurtma qatorlari bo'sh bo'lishi mumkin emas",
        "ru": "Строки заказа не могут быть пустыми",
    },
    "orders.version_conflict": {
        "uz": "Versiya konflikti: boshqa foydalanuvchi buyurtmani o'zgartirgan",
        "ru": "Конфликт версий: другой пользователь изменил заказ",
    },
    "orders.product_not_found": {
        "uz": "Mahsulot topilmadi yoki narx belgilanmagan",
        "ru": "Товар не найден или цена не установлена",
    },
    "orders.no_price": {
        "uz": "Mahsulot uchun do'kon segmentida narx topilmadi",
        "ru": "Цена для товара в сегменте магазина не найдена",
    },
    "orders.idempotency_conflict": {
        "uz": "Bu client_uuid boshqa foydalanuvchi tomonidan allaqachon ishlatilgan",
        "ru": "Данный client_uuid уже использован другим пользователем",
    },
    "orders.template_not_found": {
        "uz": "Buyurtma shabloni topilmadi",
        "ru": "Шаблон заказа не найден",
    },
    "orders.empty_template": {
        "uz": "Shablon qatorlari bo'sh bo'lishi mumkin emas",
        "ru": "Строки шаблона не могут быть пустыми",
    },

    # ── Davomat (attendance) — T16 ──────────────────────────────────────────
    "attendance.already_checked_in": {
        "uz": "Bugun allaqachon davomatga kirgan: ochiq davomat yopilmagan",
        "ru": "Вы уже отметились сегодня: открытая явка ещё не закрыта",
    },
    "attendance.not_checked_in": {
        "uz": "Bugun ochiq davomat topilmadi: avval kirish belgisi qo'ying",
        "ru": "Открытая явка на сегодня не найдена: сначала отметьтесь на вход",
    },
    "attendance.biometric_required": {
        "uz": "Biometrik tasdiqlash talab qilinadi: qurilmada biometriya o'tilmagan",
        "ru": "Требуется биометрическое подтверждение: биометрия на устройстве не пройдена",
    },
    "attendance.forbidden_user": {
        "uz": "Boshqa foydalanuvchi davomatini ko'rish taqiqlangan",
        "ru": "Просмотр явки другого пользователя запрещён",
    },

    # ── Sync (T13) ──────────────────────────────────────────────────────────
    "sync.batch_too_large": {
        "uz": "Batch hajmi oshib ketdi: maksimal {max} ta operatsiya, berilgan {given}",
        "ru": "Размер пакета превышен: максимум {max} операций, получено {given}",
    },
    "sync.rate_limited": {
        "uz": "So'rovlar soni chegarasiga yetdi, biroz kuting",
        "ru": "Превышен лимит запросов, подождите немного",
    },
    "sync.unknown_op": {
        "uz": "Noma'lum operatsiya turi",
        "ru": "Неизвестный тип операции",
    },
    "sync.invalid_cursor": {
        "uz": "Noto'g'ri kursor qiymati: musbat butun son bo'lishi kerak",
        "ru": "Неверное значение курсора: должно быть неотрицательным целым числом",
    },

    # ── GPS Ingest (T17) ─────────────────────────────────────────────────────
    "gps.batch_too_large": {
        "uz": "Batch hajmi oshib ketdi: maksimal {max} ta nuqta, berilgan {given}",
        "ru": "Размер пакета превышен: максимум {max} точек, получено {given}",
    },
    "gps.invalid_timestamp": {
        "uz": "recorded_at noto'g'ri: vaqt juda kelajakda yoki juda eski (max 30 kun)",
        "ru": "recorded_at некорректен: время слишком далеко в будущем или слишком старое (макс. 30 дней)",
    },
    "gps.forbidden_track": {
        "uz": "Boshqa foydalanuvchi GPS trek ma'lumotlarini ko'rish taqiqlangan",
        "ru": "Просмотр GPS-трека другого пользователя запрещён",
    },

    # ── Yetkazib berish (delivery) — T18 ─────────────────────────────────────
    "delivery.not_found": {
        "uz": "Yetkazish topilmadi",
        "ru": "Доставка не найдена",
    },
    "delivery.invalid_transition": {
        "uz": "Noto'g'ri holat o'tishi: '{from_status}' dan '{to_status}' ga o'tish mumkin emas",
        "ru": "Недопустимый переход состояния: из '{from_status}' в '{to_status}' невозможен",
    },
    "delivery.order_not_found": {
        "uz": "Buyurtma topilmadi yoki yetkazish uchun mos holat emas",
        "ru": "Заказ не найден или в неподходящем статусе для доставки",
    },
    "delivery.not_courier": {
        "uz": "Foydalanuvchi kuryer emas: faqat 'courier' rolidagi foydalanuvchi tayinlanishi mumkin",
        "ru": "Пользователь не является курьером: назначить можно только пользователя с ролью 'courier'",
    },
    "delivery.forbidden": {
        "uz": "Ushbu yetkazishga kirish taqiqlangan",
        "ru": "Доступ к данной доставке запрещён",
    },
    "delivery.invalid_photo": {
        "uz": "Rasm fayli noto'g'ri: faqat JPEG/PNG/WebP formatlari va 5MB gacha",
        "ru": "Некорректный файл изображения: только JPEG/PNG/WebP форматы и до 5MB",
    },
    "delivery.storage_error": {
        "uz": "Rasm saqlash xizmati hozircha mavjud emas, keyinroq urinib ko'ring",
        "ru": "Сервис хранения файлов временно недоступен, попробуйте позже",
    },
    "delivery.already_assigned": {
        "uz": "Bu buyurtma uchun aktiv yetkazish allaqachon mavjud",
        "ru": "Для этого заказа уже есть активная доставка",
    },

    # ── Push bildirishnomalar (T19) ─────────────────────────────────────────
    "push.device_token_updated": {
        "uz": "Qurilma tokeni muvaffaqiyatli yangilandi",
        "ru": "Токен устройства успешно обновлён",
    },
    "push.device_token_cleared": {
        "uz": "Qurilma tokeni o'chirildi",
        "ru": "Токен устройства удалён",
    },

    # ── Murojaat (tickets) — T24 ────────────────────────────────────────────
    "tickets.not_found": {
        "uz": "Murojaat topilmadi",
        "ru": "Обращение не найдено",
    },
    "tickets.invalid_transition": {
        "uz": "Noto'g'ri holat o'tishi: '{from_status}' dan '{to_status}' ga o'tish mumkin emas",
        "ru": "Недопустимый переход состояния: из '{from_status}' в '{to_status}' невозможен",
    },
    "tickets.forbidden": {
        "uz": "Bu amalni bajarish uchun administrator yoki buxgalter huquqi kerak",
        "ru": "Для выполнения этого действия требуются права администратора или бухгалтера",
    },
    "tickets.invalid_attachment": {
        "uz": "Ilova fayli noto'g'ri: faqat JPEG/PNG/WebP formatlari va 5MB gacha",
        "ru": "Некорректный файл вложения: только JPEG/PNG/WebP форматы и до 5MB",
    },
    "tickets.version_conflict": {
        "uz": "Versiya konflikti: boshqa foydalanuvchi murojaatni o'zgartirgan",
        "ru": "Конфликт версий: другой пользователь изменил обращение",
    },

    # ── Shartnoma (contracts) — T23 ─────────────────────────────────────────
    "contracts.not_found": {
        "uz": "Shartnoma topilmadi",
        "ru": "Договор не найден",
    },
    "contracts.duplicate_number": {
        "uz": "Bu raqamdagi shartnoma allaqachon mavjud",
        "ru": "Договор с таким номером уже существует",
    },
    "contracts.invalid_dates": {
        "uz": "Noto'g'ri sanalar: valid_to valid_from dan oldin bo'lishi mumkin emas",
        "ru": "Некорректные даты: valid_to не может быть раньше valid_from",
    },
    "contracts.invalid_file": {
        "uz": "Fayl noto'g'ri: faqat PDF, JPEG, PNG, WebP formatlari va 20MB gacha",
        "ru": "Некорректный файл: только PDF, JPEG, PNG, WebP форматы и до 20MB",
    },
    "contracts.forbidden": {
        "uz": "Bu shartnomaga kirish taqiqlangan",
        "ru": "Доступ к данному договору запрещён",
    },
    "contracts.version_conflict": {
        "uz": "Versiya konflikti: boshqa foydalanuvchi shartnomani o'zgartirgan",
        "ru": "Конфликт версий: другой пользователь изменил договор",
    },

    # ── Aksiya (promo) — T25 ────────────────────────────────────────────────
    "promo.not_found": {
        "uz": "Aksiya topilmadi",
        "ru": "Акция не найдена",
    },
    "promo.invalid_dates": {
        "uz": "Noto'g'ri sanalar: valid_to valid_from dan oldin bo'lishi mumkin emas",
        "ru": "Некорректные даты: valid_to не может быть раньше valid_from",
    },
    "promo.invalid_rule": {
        "uz": "Aksiya qoidasi yaroqsiz: rule_json noto'g'ri (discount_percent yoki discount_amount kerak)",
        "ru": "Недействительное правило акции: rule_json некорректен (требуется discount_percent или discount_amount)",
    },
    "promo.invalid_banner": {
        "uz": "Banner fayli noto'g'ri: faqat JPEG/PNG/WebP formatlari va 5MB gacha",
        "ru": "Некорректный файл баннера: только JPEG/PNG/WebP форматы и до 5MB",
    },
    "promo.version_conflict": {
        "uz": "Versiya konflikti: boshqa foydalanuvchi aksiyani o'zgartirgan",
        "ru": "Конфликт версий: другой пользователь изменил акцию",
    },

    # ── POS (Point-of-Sale) — chakana sotuv ─────────────────────────────────
    "pos.sale_not_found": {
        "uz": "Sotuv topilmadi",
        "ru": "Продажа не найдена",
    },
    "pos.empty_lines": {
        "uz": "Sotuv qatorlari bo'sh bo'lishi mumkin emas",
        "ru": "Строки продажи не могут быть пустыми",
    },
    "pos.product_not_found": {
        "uz": "Mahsulot topilmadi yoki narx belgilanmagan",
        "ru": "Товар не найден или цена не установлена",
    },
    "pos.no_price": {
        "uz": "Mahsulot uchun do'kon segmentida narx topilmadi",
        "ru": "Цена для товара в сегменте магазина не найдена",
    },
    "pos.idempotency_conflict": {
        "uz": "Bu client_uuid boshqa foydalanuvchi tomonidan allaqachon ishlatilgan",
        "ru": "Данный client_uuid уже использован другим пользователем",
    },
    "pos.invalid_payment_method": {
        "uz": "Noto'g'ri to'lov usuli: faqat 'cash' yoki 'card' qabul qilinadi",
        "ru": "Неверный способ оплаты: допустимы только 'cash' или 'card'",
    },

    # ── Statistika (stats) — T22 ────────────────────────────────────────────
    "stats.invalid_period": {
        "uz": "Noto'g'ri davr: boshlanish vaqti tugash vaqtidan katta bo'lishi mumkin emas",
        "ru": "Неверный период: дата начала не может быть позже даты окончания",
    },
    "stats.invalid_group_by": {
        "uz": "Noto'g'ri guruhlash parametri: faqat 'day', 'week', 'month' qabul qilinadi",
        "ru": "Неверный параметр группировки: допустимы только 'day', 'week', 'month'",
    },

    # ── Marketplace (MP1) ────────────────────────────────────────────────────
    "marketplace.product_not_found": {
        "uz": "Marketplace mahsuloti topilmadi",
        "ru": "Товар на маркетплейсе не найден",
    },
    "marketplace.not_published": {
        "uz": "Mahsulot marketplace'da nashr qilinmagan",
        "ru": "Товар не опубликован на маркетплейсе",
    },

    # ── Marketplace (MP2) — Buyurtma ─────────────────────────────────────────
    "marketplace.order_not_found": {
        "uz": "Marketplace buyurtmasi topilmadi",
        "ru": "Заказ на маркетплейсе не найден",
    },
    "marketplace.order_empty_lines": {
        "uz": "Buyurtma qatorlari bo'sh bo'lishi mumkin emas",
        "ru": "Строки заказа не могут быть пустыми",
    },
    "marketplace.order_mixed_suppliers": {
        "uz": "Bitta buyurtmada faqat bitta supplier korxona mahsulotlari bo'lishi shart",
        "ru": "В одном заказе могут быть товары только одного поставщика",
    },
    "marketplace.order_self_purchase": {
        "uz": "O'z korxonasidan buyurtma berish mumkin emas",
        "ru": "Нельзя оформить заказ у собственного предприятия",
    },
    "marketplace.order_no_price": {
        "uz": "Mahsulot uchun marketplace narxi topilmadi (product_id={product_id})",
        "ru": "Цена для товара на маркетплейсе не найдена (product_id={product_id})",
    },
    "marketplace.order_buyer_no_enterprise": {
        "uz": "Foydalanuvchi korxonaga tegishli emas — buyurtma berish mumkin emas",
        "ru": "Пользователь не принадлежит предприятию — оформление заказа невозможно",
    },
    "marketplace.order_invalid_transition": {
        "uz": "Noto'g'ri holat o'tishi: '{from_status}' dan '{to_status}' ga o'tish mumkin emas",
        "ru": "Недопустимый переход состояния: из '{from_status}' в '{to_status}' невозможен",
    },
    "marketplace.order_supplier_only": {
        "uz": "Bu amalni faqat supplier korxona bajarishi mumkin",
        "ru": "Это действие может выполнить только поставщик",
    },
    "marketplace.order_idempotency_conflict": {
        "uz": "Bu client_uuid boshqa foydalanuvchi tomonidan allaqachon ishlatilgan",
        "ru": "Данный client_uuid уже использован другим пользователем",
    },

    # ── Marketplace (MP3) — Yetkazish oqimi ─────────────────────────────────
    "marketplace.courier_not_found": {
        "uz": "Kuryer topilmadi yoki ushbu korxonaga tegishli emas",
        "ru": "Курьер не найден или не принадлежит данному предприятию",
    },
    "marketplace.order_courier_mismatch": {
        "uz": "Faqat tayinlangan kuryer yetkazilganini tasdiqlay oladi",
        "ru": "Только назначенный курьер может подтвердить доставку",
    },
    "marketplace.order_buyer_only": {
        "uz": "Bu amalni faqat buyer korxona bajarishi mumkin",
        "ru": "Это действие может выполнить только покупатель",
    },
    "marketplace.accept_no_store": {
        "uz": "Qabul qilish uchun do'kon ko'rsatilmagan va buyurtmada buyer_store_id yo'q",
        "ru": "Не указан магазин для приёмки, а в заказе отсутствует buyer_store_id",
    },
    "marketplace.accept_store_not_found": {
        "uz": "Ko'rsatilgan do'kon ushbu korxonaga tegishli emas yoki topilmadi",
        "ru": "Указанный магазин не принадлежит данному предприятию или не найден",
    },

    # ── Umumiy ──────────────────────────────────────────────────────────────
    "common.not_found": {
        "uz": "So'ralgan resurs topilmadi",
        "ru": "Запрашиваемый ресурс не найден",
    },
    "common.validation_error": {
        "uz": "So'rov ma'lumotlari noto'g'ri",
        "ru": "Данные запроса некорректны",
    },
    "common.internal_error": {
        "uz": "Ichki server xatosi",
        "ru": "Внутренняя ошибка сервера",
    },
}


# ─── translate() ─────────────────────────────────────────────────────────────

def translate(message_key: str, locale: str | None = None, **params: object) -> str:
    """
    message_key va locale bo'yicha lokalizatsiyalangan matn qaytaradi.

    Parametrlar {param} o'rinbosar bilan formatlanadi.

    Fallback zanjiri:
      1. MESSAGES[message_key][locale] → to'g'ri tarjima.
      2. MESSAGES[message_key]["uz"]   → standart tilda fallback.
      3. Kalit topilmasa              → message_key o'zi qaytadi.

    Args:
        message_key: Xabar kaliti (masalan, "auth.invalid_credentials").
        locale: Til kodi ("uz" yoki "ru"). None bo'lsa current_locale ishlatiladi.
        **params: Shablon uchun parametrlar (masalan, module="catalog", action="delete").

    Returns:
        Lokalizatsiyalangan va formatlanagan matn string.
    """
    # Import shu yerda (circular import dan saqlanish uchun)
    from app.core.i18n import current_locale, SUPPORTED_LOCALES, DEFAULT_LOCALE

    if locale is None:
        locale = current_locale.get()

    if locale not in SUPPORTED_LOCALES:
        locale = DEFAULT_LOCALE

    catalog = MESSAGES.get(message_key)
    if catalog is None:
        # LOW: Noma'lum kalit — warning log + graceful fallback (kalit o'zi qaytadi)
        _logger.warning("translate: unknown message_key=%s", message_key)
        return message_key

    # Asosiy tarjima yoki uz fallback
    template = catalog.get(locale) or catalog.get(DEFAULT_LOCALE) or message_key

    # Parametrlar bilan formatlash (KeyError xavfsiz)
    if params:
        try:
            return template.format(**params)
        except (KeyError, ValueError):
            return template

    return template
