"""Best-effort Telegram notifications, usable from both the bot and the API.

Sends via the Bot HTTP API directly (httpx), so it works in the API process too,
which has no aiogram Bot object. Every call is best-effort: failures (user never
started the bot, blocked it, bad id) are logged and swallowed — a notification must
never break the tier/purchase flow that triggered it.
"""

import html
import logging

import httpx

from app.config import settings
from app.tiers import tier_title

logger = logging.getLogger(__name__)

_TELEGRAM_API = "https://api.telegram.org"


async def send_message(chat_id: int, text: str) -> bool:
    if not settings.BOT_TOKEN:
        return False
    url = f"{_TELEGRAM_API}/bot{settings.BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, json=payload)
        if response.status_code != 200:
            logger.warning("Telegram sendMessage to %s failed: %s %s", chat_id, response.status_code, response.text)
            return False
        return True
    except Exception:
        logger.warning("Telegram sendMessage to %s errored", chat_id, exc_info=True)
        return False


async def notify_tier_changed(telegram_id: int, tier: str | None) -> None:
    """Tell a user their tier was changed by the trainer/site."""
    if tier is None:
        text = (
            "ℹ️ Твій доступ до тренувань оновлено: <b>наразі активного доступу немає</b>.\n\n"
            "Якщо це помилка — напиши тренеру."
        )
    else:
        text = (
            f"ℹ️ Твій тариф оновлено: <b>{tier_title(tier)}</b>.\n\n"
            "Відкрий /catalog — тренування вже доступні 🌿"
        )
    await send_message(telegram_id, text)


async def notify_admins_new_access(
    buyer_id: int,
    buyer_name: str,
    buyer_username: str | None,
    tier: str,
) -> None:
    """Tell every admin that a user just activated access (bound to the bot)."""
    name = html.escape(buyer_name or "—")
    handle = f" (@{html.escape(buyer_username)})" if buyer_username else ""
    text = (
        "🎉 <b>Новий доступ активовано</b>\n\n"
        f"Клієнт: {name}{handle}\n"
        f"ID: <code>{buyer_id}</code>\n"
        f"Тариф: <b>{tier_title(tier)}</b>"
    )
    for admin_id in settings.admin_ids:
        await send_message(admin_id, text)
