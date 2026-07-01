"""User-facing video catalog: browse groups -> subgroups -> videos.

Everything here is tier-gated: a user must have an active (non-expired) tier, and
only sees content whose ``min_tier`` is at or below his tier.
"""

import logging
from datetime import UTC, datetime

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.config import settings
from app.services.catalog_service import CatalogService
from app.services.token_service import ActiveAccess, TokenService
from app.tiers import tier_title

router = Router(name=__name__)
logger = logging.getLogger(__name__)

CATALOG_TITLE = "🎬 Мої тренування"
FROZEN_NOTE = "⏸ Доступ до тренувань тимчасово призупинено. Ми скоро все повернемо 🌿"
FROZEN_ALERT = "Тренування тимчасово недоступні"


def support_button() -> list[InlineKeyboardButton]:
    if not settings.SUPPORT_USERNAME:
        return []
    username = settings.SUPPORT_USERNAME.removeprefix("@")
    return [InlineKeyboardButton(text="✍️ Написати тренеру", url=f"https://t.me/{username}")]


def no_access_markup() -> InlineKeyboardMarkup:
    rows = []
    support = support_button()
    if support:
        rows.append(support)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def days_left(expires_at: datetime) -> int:
    delta = expires_at - datetime.now(UTC)
    return max(0, delta.days)


def access_header(access: ActiveAccess) -> str:
    return (
        f"Тариф: <b>{tier_title(access.tier)}</b> · "
        f"залишилось <b>{days_left(access.expires_at)}</b> дн.\n"
    )


async def require_access(telegram_id: int, token_service: TokenService) -> ActiveAccess | None:
    return await token_service.get_active_access(telegram_id)


async def send_no_access(message: Message) -> None:
    await message.answer(
        "У тебе поки немає активного доступу 🔒\n\n"
        "Після оплати на сайті відкрий персональне посилання — і я активую доступ. "
        "Якщо доступ закінчився, його можна продовжити на сайті.",
        reply_markup=no_access_markup(),
    )


def build_home_markup(groups, access: ActiveAccess) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"📁 {group.title}", callback_data=f"cat:grp:{group.id}")] for group in groups]
    support = support_button()
    if support:
        rows.append(support)
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def render_home(telegram_id: int, token_service: TokenService, catalog_service: CatalogService) -> tuple[str, InlineKeyboardMarkup] | None:
    access = await require_access(telegram_id, token_service)
    if access is None:
        return None

    if await token_service.is_tier_frozen(access.tier):
        text = CATALOG_TITLE + "\n\n" + access_header(access) + "\n" + FROZEN_NOTE
        return text, no_access_markup()

    groups = await catalog_service.visible_groups(parent_id=None, user_tier=access.tier)
    text = CATALOG_TITLE + "\n\n" + access_header(access)
    if groups:
        text += "\nОбери розділ:"
    else:
        text += "\nРозділи ще наповнюються. Зазирни трохи пізніше 🌿"
    return text, build_home_markup(groups, access)


@router.message(Command("catalog"))
@router.message(Command("mycourses"))
@router.message(Command("myaccess"))
async def catalog_command(message: Message, token_service: TokenService, catalog_service: CatalogService) -> None:
    if message.from_user is None:
        return
    rendered = await render_home(message.from_user.id, token_service, catalog_service)
    if rendered is None:
        await send_no_access(message)
        return
    text, markup = rendered
    await message.answer(text, reply_markup=markup, parse_mode="HTML")


@router.callback_query(F.data == "cat:home")
async def open_home(callback: CallbackQuery, token_service: TokenService, catalog_service: CatalogService) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    rendered = await render_home(callback.from_user.id, token_service, catalog_service)
    if rendered is None:
        await callback.answer("Доступ неактивний", show_alert=True)
        return
    text, markup = rendered
    await edit_or_send(callback, text, markup)
    await callback.answer()


@router.callback_query(F.data.startswith("cat:grp:"))
async def open_group(callback: CallbackQuery, token_service: TokenService, catalog_service: CatalogService) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return

    access = await require_access(callback.from_user.id, token_service)
    if access is None:
        await callback.answer("Доступ неактивний", show_alert=True)
        return
    if await token_service.is_tier_frozen(access.tier):
        await callback.answer(FROZEN_ALERT, show_alert=True)
        return

    group_id = int(callback.data.removeprefix("cat:grp:"))
    group = await catalog_service.get_group_if_visible(group_id, access.tier)
    if group is None:
        await callback.answer("Розділ недоступний", show_alert=True)
        return

    subgroups = await catalog_service.visible_groups(parent_id=group.id, user_tier=access.tier)
    videos = await catalog_service.visible_videos(group_id=group.id, user_tier=access.tier)

    rows: list[list[InlineKeyboardButton]] = []
    for sub in subgroups:
        rows.append([InlineKeyboardButton(text=f"📁 {sub.title}", callback_data=f"cat:grp:{sub.id}")])
    for video in videos:
        rows.append([InlineKeyboardButton(text=f"▶️ {video.title}", callback_data=f"cat:vid:{video.id}")])

    back = "cat:home" if group.parent_id is None else f"cat:grp:{group.parent_id}"
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=back)])

    text = f"📁 <b>{group.title}</b>\n\n" + access_header(access)
    if not subgroups and not videos:
        text += "\nТут поки порожньо."
    await edit_or_send(callback, text, InlineKeyboardMarkup(inline_keyboard=rows))
    await callback.answer()


@router.callback_query(F.data.startswith("cat:vid:"))
async def open_video(callback: CallbackQuery, token_service: TokenService, catalog_service: CatalogService) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return

    access = await require_access(callback.from_user.id, token_service)
    if access is None:
        await callback.answer("Доступ неактивний", show_alert=True)
        return
    if await token_service.is_tier_frozen(access.tier):
        await callback.answer(FROZEN_ALERT, show_alert=True)
        return

    video_id = int(callback.data.removeprefix("cat:vid:"))
    video = await catalog_service.get_video_if_visible(video_id, access.tier)
    if video is None:
        await callback.answer("Відео недоступне", show_alert=True)
        return

    watch_row = [InlineKeyboardButton(text="▶️ Дивитись", url=video.youtube_url)]
    back_row = [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"cat:grp:{video.group_id}")]
    markup = InlineKeyboardMarkup(inline_keyboard=[watch_row, back_row])

    caption = f"▶️ <b>{video.title}</b>"
    if video.thumbnail_url:
        try:
            await callback.message.answer_photo(
                photo=video.thumbnail_url,
                caption=caption,
                reply_markup=markup,
                parse_mode="HTML",
            )
            await callback.answer()
            return
        except Exception:
            logger.warning("Failed to send thumbnail for video_id=%s", video.id)

    await callback.message.answer(caption, reply_markup=markup, parse_mode="HTML")
    await callback.answer()


async def edit_or_send(callback: CallbackQuery, text: str, markup: InlineKeyboardMarkup) -> None:
    """Edit the current message if it's text; otherwise send a fresh one.

    Messages that carry a photo (video cards) can't be edited into plain text, so
    we fall back to sending a new message.
    """
    message = callback.message
    if message is None:
        return
    try:
        await message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    except Exception:
        await message.answer(text, reply_markup=markup, parse_mode="HTML")


@router.message(CommandStart())
async def start_handler(message: Message, token_service: TokenService, catalog_service: CatalogService) -> None:
    """Plain /start (no token). Show the catalog if access is active, else a hint."""
    if message.from_user is None:
        return
    rendered = await render_home(message.from_user.id, token_service, catalog_service)
    if rendered is None:
        await message.answer(
            "Привіт! 🌸\n\n"
            "Це бот із відеотренуваннями. Після оплати на сайті відкрий персональне "
            "посилання — я активую доступ, і тут зʼявляться твої тренування.",
            reply_markup=no_access_markup(),
        )
        return
    text, markup = rendered
    await message.answer(text, reply_markup=markup, parse_mode="HTML")


@router.message(Command("help"))
async def help_handler(message: Message) -> None:
    text = (
        "Команди:\n"
        "/catalog — мої тренування\n"
        "/myaccess — мій доступ і термін\n"
        "/activate TOKEN — активувати доступ вручну\n"
    )
    if message.from_user is not None and message.from_user.id in settings.admin_ids:
        text += (
            "\nАдмін:\n"
            "/admin — панель: контент, тариф користувача, заморозка тарифів\n"
            "/grant ID ТАРИФ [ДНІ] — видати доступ вручну (без оплати)\n"
            "/revoke ID — закрити доступ достроково\n"
            "/access ID — перевірити доступ клієнта"
        )
    rows = []
    support = support_button()
    if support:
        rows.append(support)
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
