"""Admin access control: manually grant free access or revoke it early.

Payments are one-off (a tier grant that auto-expires), so there is nothing to
"unsubscribe" on the billing side. These commands cover the two things the owner
can't do from the payment flow: hand someone access without payment, and cut a
user's access off before it expires.

Owner-only. A user is addressed by their numeric Telegram id (the reliable
identifier); the person can learn theirs from the bot, or the owner sees it in the
support chat.
"""

import logging

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from app.handlers.admin_panel import is_admin
from app.services.token_service import InvalidTierError, TokenService
from app.tiers import ALL_TIERS, tier_title

router = Router(name=__name__)
logger = logging.getLogger(__name__)

_TIERS_HINT = " / ".join(ALL_TIERS)


@router.message(Command("grant"))
async def grant_command(message: Message, command: CommandObject, token_service: TokenService) -> None:
    if not is_admin(message.from_user.id if message.from_user else None):
        return

    parts = (command.args or "").split()
    if len(parts) < 2:
        await message.answer(
            "Видати доступ вручну (без оплати):\n"
            f"<code>/grant ID ТАРИФ [ДНІ]</code>\n\n"
            f"ТАРИФ: {_TIERS_HINT}\n"
            "ДНІ — необовʼязково (за замовчуванням строк тарифу).\n\n"
            "Приклад: <code>/grant 123456789 pro 30</code>\n\n"
            "ID — це номер акаунта клієнта в Telegram. Щоб його дізнатись, "
            "попроси клієнта відкрити бота @userinfobot — той покаже його ID.",
            parse_mode="HTML",
        )
        return

    raw_id, raw_tier = parts[0], parts[1]
    if not raw_id.lstrip("-").isdigit():
        await message.answer("Перший аргумент має бути числовим ID Telegram. Приклад: /grant 123456789 pro 30")
        return
    telegram_id = int(raw_id)

    duration_days: int | None = None
    if len(parts) >= 3:
        if not parts[2].isdigit() or int(parts[2]) <= 0:
            await message.answer("ДНІ мають бути додатним числом. Приклад: /grant 123456789 pro 30")
            return
        duration_days = int(parts[2])

    try:
        granted = await token_service.grant_access_manually(
            telegram_id=telegram_id,
            tier=raw_tier,
            duration_days=duration_days,
            granted_by_tg_id=message.from_user.id if message.from_user else None,
        )
    except InvalidTierError:
        await message.answer(f"Невідомий тариф «{raw_tier}». Доступні: {_TIERS_HINT}.")
        return

    await message.answer(
        "✅ Доступ видано вручну.\n\n"
        f"Клієнт (ID <code>{telegram_id}</code>): тариф <b>{tier_title(granted.tier)}</b>\n"
        f"Діє до: <b>{granted.expires_at.strftime('%d.%m.%Y')}</b>\n\n"
        "Клієнт побачить тренування одразу — хай відкриє бота й натисне /catalog.",
        parse_mode="HTML",
    )


@router.message(Command("revoke"))
async def revoke_command(message: Message, command: CommandObject, token_service: TokenService) -> None:
    if not is_admin(message.from_user.id if message.from_user else None):
        return

    raw_id = (command.args or "").strip()
    if not raw_id.lstrip("-").isdigit():
        await message.answer(
            "Закрити доступ достроково:\n"
            "<code>/revoke ID</code>\n\n"
            "Приклад: <code>/revoke 123456789</code>\n"
            "ID — номер акаунта клієнта в Telegram.",
            parse_mode="HTML",
        )
        return

    telegram_id = int(raw_id)
    revoked = await token_service.revoke_access(
        telegram_id=telegram_id,
        revoked_by_tg_id=message.from_user.id if message.from_user else None,
    )

    if revoked is None:
        await message.answer(f"У клієнта (ID <code>{telegram_id}</code>) не було активного доступу.", parse_mode="HTML")
        return

    await message.answer(
        "🚫 Доступ закрито.\n\n"
        f"Клієнт (ID <code>{telegram_id}</code>): тариф <b>{tier_title(revoked.tier)}</b> більше не діє.\n"
        "Тренування в боті одразу стануть недоступні.",
        parse_mode="HTML",
    )


@router.message(Command("access"))
async def access_command(message: Message, command: CommandObject, token_service: TokenService) -> None:
    if not is_admin(message.from_user.id if message.from_user else None):
        return

    raw_id = (command.args or "").strip()
    if not raw_id.lstrip("-").isdigit():
        await message.answer(
            "Перевірити доступ клієнта:\n"
            "<code>/access ID</code>\n\n"
            "Приклад: <code>/access 123456789</code>",
            parse_mode="HTML",
        )
        return

    telegram_id = int(raw_id)
    access = await token_service.get_active_access(telegram_id)
    if access is None:
        await message.answer(f"У клієнта (ID <code>{telegram_id}</code>) немає активного доступу.", parse_mode="HTML")
        return

    await message.answer(
        f"Клієнт (ID <code>{telegram_id}</code>):\n"
        f"тариф <b>{tier_title(access.tier)}</b>, діє до <b>{access.expires_at.strftime('%d.%m.%Y')}</b>.",
        parse_mode="HTML",
    )


@router.message(Command("myid"))
async def myid_command(message: Message) -> None:
    """Anyone can learn their own Telegram id — needed so the owner can /grant them."""
    if message.from_user is None:
        return
    await message.answer(
        f"Твій ID у Telegram: <code>{message.from_user.id}</code>\n"
        "Надішли його тренеру, щоб отримати доступ.",
        parse_mode="HTML",
    )
