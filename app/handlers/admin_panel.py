"""Admin panel: manage the video catalog from inside Telegram.

The owner builds groups -> subgroups -> videos, adds videos by pasting a YouTube
link (title + cover auto-parsed), and sets the minimum tier per group/video.

Single-step FSM flows only: a button arms a state, the next text message completes
it. Tier selection and navigation are pure inline callbacks (no state).
"""

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.config import settings
from app.repositories.content_group_repository import ContentGroupRepository
from app.repositories.tier_flag_repository import TierFlagRepository
from app.repositories.video_repository import VideoRepository
from app.services.notifications import notify_tier_changed
from app.services.token_service import InvalidTierError, TokenService
from app.services.youtube_parser import (
    YoutubeCourseParser,
    YoutubeLinkNotFoundError,
    YoutubeParseError,
)
from app.tiers import ALL_TIERS, ASSIGNABLE_TIERS, TIER_NONE, normalize_tier, tier_title

router = Router(name=__name__)
logger = logging.getLogger(__name__)


class AdminStates(StatesGroup):
    group_title = State()    # data: parent_id (int | None)
    group_rename = State()   # data: group_id
    video_link = State()     # data: group_id
    video_rename = State()   # data: video_id
    user_tier_id = State()   # waiting for the Telegram id to set a tier for


def is_admin(user_id: int | None) -> bool:
    return user_id is not None and user_id in settings.admin_ids


def tier_picker_row(kind: str, item_id: int) -> list[InlineKeyboardButton]:
    # kind: "g" (group) | "v" (video)
    return [
        InlineKeyboardButton(text=tier_title(tier), callback_data=f"adm:settier:{kind}:{item_id}:{tier}")
        for tier in ALL_TIERS
    ]


# ----------------------------------------------------------------------------
# Home
# ----------------------------------------------------------------------------

async def render_home() -> tuple[str, InlineKeyboardMarkup]:
    rows = [
        [InlineKeyboardButton(text="📂 Розділи каталогу", callback_data="adm:catalog")],
        [InlineKeyboardButton(text="👤 Тариф користувача", callback_data="adm:utier:start")],
        [InlineKeyboardButton(text="🧊 Доступ по тарифах", callback_data="adm:freeze:menu")],
    ]
    text = "🛠 <b>Адмін-панель</b>\n\nОбери, що робимо:"
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


async def render_catalog(content_group_repository: ContentGroupRepository) -> tuple[str, InlineKeyboardMarkup]:
    groups = await content_group_repository.list_children(parent_id=None, active_only=False)
    rows = [
        [InlineKeyboardButton(
            text=f"📁 {group.title} · {tier_title(group.min_tier)}",
            callback_data=f"adm:grp:{group.id}",
        )]
        for group in groups
    ]
    rows.append([InlineKeyboardButton(text="➕ Нова група", callback_data="adm:newgrp:root")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="adm:home")])
    text = (
        "📂 <b>Розділи каталогу</b>\n\nОбери розділ або створи новий:"
        if groups
        else "📂 <b>Розділи каталогу</b>\n\nЩе немає жодного розділу."
    )
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("admin"))
async def admin_command(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id if message.from_user else None):
        return
    await state.clear()
    text, markup = await render_home()
    await message.answer(text, reply_markup=markup, parse_mode="HTML")


@router.callback_query(F.data == "adm:home")
async def admin_home(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id if callback.from_user else None):
        await callback.answer("Немає доступу", show_alert=True)
        return
    await state.clear()
    text, markup = await render_home()
    await safe_edit(callback, text, markup)
    await callback.answer()


@router.callback_query(F.data == "adm:catalog")
async def open_admin_catalog(callback: CallbackQuery, content_group_repository: ContentGroupRepository, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id if callback.from_user else None):
        await callback.answer("Немає доступу", show_alert=True)
        return
    await state.clear()
    text, markup = await render_catalog(content_group_repository)
    await safe_edit(callback, text, markup)
    await callback.answer()


# ----------------------------------------------------------------------------
# Group management
# ----------------------------------------------------------------------------

async def render_group(
    group_id: int,
    content_group_repository: ContentGroupRepository,
    video_repository: VideoRepository,
) -> tuple[str, InlineKeyboardMarkup] | None:
    group = await content_group_repository.get_by_id(group_id)
    if group is None:
        return None

    subgroups = await content_group_repository.list_children(parent_id=group.id, active_only=False)
    videos = await video_repository.list_by_group(group.id, active_only=False)

    rows: list[list[InlineKeyboardButton]] = []
    for sub in subgroups:
        rows.append([InlineKeyboardButton(
            text=f"📁 {sub.title} · {tier_title(sub.min_tier)}",
            callback_data=f"adm:grp:{sub.id}",
        )])
    for video in videos:
        rows.append([InlineKeyboardButton(
            text=f"▶️ {video.title} · {tier_title(video.min_tier)}",
            callback_data=f"adm:vid:{video.id}",
        )])

    rows.append([
        InlineKeyboardButton(text="➕ Підгрупа", callback_data=f"adm:newgrp:{group.id}"),
        InlineKeyboardButton(text="➕ Відео", callback_data=f"adm:newvid:{group.id}"),
    ])
    rows.append([
        InlineKeyboardButton(text="✏️ Назва", callback_data=f"adm:ren:g:{group.id}"),
        InlineKeyboardButton(text="🗑 Видалити", callback_data=f"adm:del:g:{group.id}"),
    ])
    rows.append(tier_picker_row("g", group.id))
    back = "adm:catalog" if group.parent_id is None else f"adm:grp:{group.parent_id}"
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=back)])

    text = (
        f"📁 <b>{group.title}</b>\n"
        f"Мінімальний тариф: <b>{tier_title(group.min_tier)}</b>\n\n"
        f"Підгруп: {len(subgroups)} · Відео: {len(videos)}\n\n"
        "Тариф нижче — мінімальний рівень, з якого видно цей розділ."
    )
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("adm:grp:"))
async def open_admin_group(
    callback: CallbackQuery,
    content_group_repository: ContentGroupRepository,
    video_repository: VideoRepository,
    state: FSMContext,
) -> None:
    if not is_admin(callback.from_user.id if callback.from_user else None):
        await callback.answer("Немає доступу", show_alert=True)
        return
    await state.clear()
    group_id = int(callback.data.removeprefix("adm:grp:"))
    rendered = await render_group(group_id, content_group_repository, video_repository)
    if rendered is None:
        await callback.answer("Розділ не знайдено", show_alert=True)
        return
    text, markup = rendered
    await safe_edit(callback, text, markup)
    await callback.answer()


@router.callback_query(F.data.startswith("adm:newgrp:"))
async def new_group_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id if callback.from_user else None):
        await callback.answer("Немає доступу", show_alert=True)
        return
    raw_parent = callback.data.removeprefix("adm:newgrp:")
    parent_id = None if raw_parent == "root" else int(raw_parent)
    await state.set_state(AdminStates.group_title)
    await state.update_data(parent_id=parent_id)
    where = "групи" if parent_id is None else "підгрупи"
    await callback.message.answer(f"Надішли назву нової {where}:")
    await callback.answer()


@router.message(AdminStates.group_title)
async def new_group_finish(
    message: Message,
    state: FSMContext,
    content_group_repository: ContentGroupRepository,
    video_repository: VideoRepository,
) -> None:
    title = (message.text or "").strip()
    if not title:
        await message.answer("Назва порожня. Спробуй ще раз.")
        return
    data = await state.get_data()
    parent_id = data.get("parent_id")

    min_tier = "lite"
    if parent_id is not None:
        parent = await content_group_repository.get_by_id(parent_id)
        if parent is not None:
            min_tier = parent.min_tier

    group = await content_group_repository.create(title=title[:128], parent_id=parent_id, min_tier=min_tier)
    await state.clear()

    rendered = await render_group(group.id, content_group_repository, video_repository)
    if rendered is not None:
        text, markup = rendered
        await message.answer("✅ Створено.", )
        await message.answer(text, reply_markup=markup, parse_mode="HTML")


@router.callback_query(F.data.startswith("adm:ren:g:"))
async def rename_group_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id if callback.from_user else None):
        await callback.answer("Немає доступу", show_alert=True)
        return
    group_id = int(callback.data.removeprefix("adm:ren:g:"))
    await state.set_state(AdminStates.group_rename)
    await state.update_data(group_id=group_id)
    await callback.message.answer("Надішли нову назву розділу:")
    await callback.answer()


@router.message(AdminStates.group_rename)
async def rename_group_finish(
    message: Message,
    state: FSMContext,
    content_group_repository: ContentGroupRepository,
    video_repository: VideoRepository,
) -> None:
    title = (message.text or "").strip()
    if not title:
        await message.answer("Назва порожня. Спробуй ще раз.")
        return
    data = await state.get_data()
    group_id = int(data["group_id"])
    group = await content_group_repository.get_by_id(group_id)
    if group is None:
        await state.clear()
        await message.answer("Розділ не знайдено.")
        return
    await content_group_repository.update(group, title=title[:128])
    await state.clear()
    rendered = await render_group(group_id, content_group_repository, video_repository)
    if rendered is not None:
        text, markup = rendered
        await message.answer(text, reply_markup=markup, parse_mode="HTML")


@router.callback_query(F.data.startswith("adm:del:g:"))
async def delete_group_confirm(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id if callback.from_user else None):
        await callback.answer("Немає доступу", show_alert=True)
        return
    group_id = int(callback.data.removeprefix("adm:del:g:"))
    markup = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Так, видалити", callback_data=f"adm:delyes:g:{group_id}"),
        InlineKeyboardButton(text="↩️ Скасувати", callback_data=f"adm:grp:{group_id}"),
    ]])
    await safe_edit(callback, "🗑 Видалити розділ разом з усіма підгрупами та відео?", markup)
    await callback.answer()


@router.callback_query(F.data.startswith("adm:delyes:g:"))
async def delete_group(
    callback: CallbackQuery,
    content_group_repository: ContentGroupRepository,
    video_repository: VideoRepository,
) -> None:
    if not is_admin(callback.from_user.id if callback.from_user else None):
        await callback.answer("Немає доступу", show_alert=True)
        return
    group_id = int(callback.data.removeprefix("adm:delyes:g:"))
    group = await content_group_repository.get_by_id(group_id)
    parent_id = group.parent_id if group else None
    if group is not None:
        await content_group_repository.delete(group)
    await callback.answer("Видалено")
    if parent_id is None:
        text, markup = await render_catalog(content_group_repository)
        await safe_edit(callback, text, markup)
        return
    rendered = await render_group(parent_id, content_group_repository, video_repository)
    if rendered is not None:
        text, markup = rendered
        await safe_edit(callback, text, markup)
    else:
        text, markup = await render_catalog(content_group_repository)
        await safe_edit(callback, text, markup)


# ----------------------------------------------------------------------------
# Video management
# ----------------------------------------------------------------------------

async def render_video(video_id: int, video_repository: VideoRepository) -> tuple[str, InlineKeyboardMarkup] | None:
    video = await video_repository.get_by_id(video_id)
    if video is None:
        return None
    rows = [
        [
            InlineKeyboardButton(text="✏️ Назва", callback_data=f"adm:ren:v:{video.id}"),
            InlineKeyboardButton(text="🗑 Видалити", callback_data=f"adm:del:v:{video.id}"),
        ],
        tier_picker_row("v", video.id),
        [InlineKeyboardButton(text="⬅️ До групи", callback_data=f"adm:grp:{video.group_id}")],
    ]
    text = (
        f"▶️ <b>{video.title}</b>\n"
        f"Мінімальний тариф: <b>{tier_title(video.min_tier)}</b>\n"
        f"Посилання: {video.youtube_url}\n"
        f"Обкладинка: {'є' if video.thumbnail_url else 'немає'}"
    )
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("adm:vid:"))
async def open_admin_video(callback: CallbackQuery, video_repository: VideoRepository, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id if callback.from_user else None):
        await callback.answer("Немає доступу", show_alert=True)
        return
    await state.clear()
    video_id = int(callback.data.removeprefix("adm:vid:"))
    rendered = await render_video(video_id, video_repository)
    if rendered is None:
        await callback.answer("Відео не знайдено", show_alert=True)
        return
    text, markup = rendered
    await safe_edit(callback, text, markup)
    await callback.answer()


@router.callback_query(F.data.startswith("adm:newvid:"))
async def new_video_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id if callback.from_user else None):
        await callback.answer("Немає доступу", show_alert=True)
        return
    group_id = int(callback.data.removeprefix("adm:newvid:"))
    await state.set_state(AdminStates.video_link)
    await state.update_data(group_id=group_id)
    await callback.message.answer(
        "Надішли посилання на відео YouTube (краще «Доступ за посиланням»/unlisted).\n"
        "Назву й обкладинку я підтягну сам."
    )
    await callback.answer()


@router.message(AdminStates.video_link)
async def new_video_finish(
    message: Message,
    state: FSMContext,
    content_group_repository: ContentGroupRepository,
    video_repository: VideoRepository,
) -> None:
    text = (message.text or message.caption or "").strip()
    data = await state.get_data()
    group_id = int(data["group_id"])
    group = await content_group_repository.get_by_id(group_id)
    if group is None:
        await state.clear()
        await message.answer("Розділ не знайдено.")
        return

    parser = YoutubeCourseParser(cookies_file=settings.YOUTUBE_COOKIES_FILE or None)
    status = await message.answer("⏳ Читаю відео з YouTube…")
    try:
        parsed = await parser.parse(text)
    except YoutubeLinkNotFoundError:
        await status.edit_text("Не знайшов YouTube-посилання. Надішли коректне посилання ще раз.")
        return
    except YoutubeParseError as error:
        logger.warning("Failed to parse video: %s", error)
        await status.edit_text(
            "Не вдалося відкрити відео. Перевір, що воно «Доступ за посиланням», а не повністю приватне."
        )
        return
    except Exception:
        logger.exception("Unexpected video parse error")
        await status.edit_text("Неочікувана помилка під час читання відео.")
        return

    video = await video_repository.create(
        group_id=group_id,
        title=parsed.title[:128],
        youtube_url=parsed.url,
        thumbnail_url=parsed.thumbnail_url,
        min_tier=group.min_tier,
    )
    await state.clear()
    await status.edit_text("✅ Відео додано.")
    rendered = await render_video(video.id, video_repository)
    if rendered is not None:
        vtext, markup = rendered
        await message.answer(vtext, reply_markup=markup, parse_mode="HTML")


@router.callback_query(F.data.startswith("adm:ren:v:"))
async def rename_video_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id if callback.from_user else None):
        await callback.answer("Немає доступу", show_alert=True)
        return
    video_id = int(callback.data.removeprefix("adm:ren:v:"))
    await state.set_state(AdminStates.video_rename)
    await state.update_data(video_id=video_id)
    await callback.message.answer("Надішли нову назву відео:")
    await callback.answer()


@router.message(AdminStates.video_rename)
async def rename_video_finish(message: Message, state: FSMContext, video_repository: VideoRepository) -> None:
    title = (message.text or "").strip()
    if not title:
        await message.answer("Назва порожня. Спробуй ще раз.")
        return
    data = await state.get_data()
    video_id = int(data["video_id"])
    video = await video_repository.get_by_id(video_id)
    if video is None:
        await state.clear()
        await message.answer("Відео не знайдено.")
        return
    await video_repository.update(video, title=title[:128])
    await state.clear()
    rendered = await render_video(video_id, video_repository)
    if rendered is not None:
        text, markup = rendered
        await message.answer(text, reply_markup=markup, parse_mode="HTML")


@router.callback_query(F.data.startswith("adm:del:v:"))
async def delete_video_confirm(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id if callback.from_user else None):
        await callback.answer("Немає доступу", show_alert=True)
        return
    video_id = int(callback.data.removeprefix("adm:del:v:"))
    markup = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Так, видалити", callback_data=f"adm:delyes:v:{video_id}"),
        InlineKeyboardButton(text="↩️ Скасувати", callback_data=f"adm:vid:{video_id}"),
    ]])
    await safe_edit(callback, "🗑 Видалити це відео?", markup)
    await callback.answer()


@router.callback_query(F.data.startswith("adm:delyes:v:"))
async def delete_video(
    callback: CallbackQuery,
    video_repository: VideoRepository,
    content_group_repository: ContentGroupRepository,
) -> None:
    if not is_admin(callback.from_user.id if callback.from_user else None):
        await callback.answer("Немає доступу", show_alert=True)
        return
    video_id = int(callback.data.removeprefix("adm:delyes:v:"))
    video = await video_repository.get_by_id(video_id)
    group_id = video.group_id if video else None
    if video is not None:
        await video_repository.delete(video)
    await callback.answer("Видалено")
    if group_id is not None:
        rendered = await render_group(group_id, content_group_repository, video_repository)
        if rendered is not None:
            text, markup = rendered
            await safe_edit(callback, text, markup)


# ----------------------------------------------------------------------------
# Tier selection (groups + videos)
# ----------------------------------------------------------------------------

@router.callback_query(F.data.startswith("adm:settier:"))
async def set_tier(
    callback: CallbackQuery,
    content_group_repository: ContentGroupRepository,
    video_repository: VideoRepository,
) -> None:
    if not is_admin(callback.from_user.id if callback.from_user else None):
        await callback.answer("Немає доступу", show_alert=True)
        return
    # adm:settier:<kind>:<id>:<tier>
    _, _, kind, raw_id, raw_tier = callback.data.split(":")
    try:
        tier = normalize_tier(raw_tier)
    except ValueError:
        await callback.answer("Невідомий тариф", show_alert=True)
        return
    item_id = int(raw_id)

    if kind == "g":
        group = await content_group_repository.get_by_id(item_id)
        if group is None:
            await callback.answer("Розділ не знайдено", show_alert=True)
            return
        await content_group_repository.update(group, min_tier=tier)
        rendered = await render_group(item_id, content_group_repository, video_repository)
    else:
        video = await video_repository.get_by_id(item_id)
        if video is None:
            await callback.answer("Відео не знайдено", show_alert=True)
            return
        await video_repository.update(video, min_tier=tier)
        rendered = await render_video(item_id, video_repository)

    await callback.answer(f"Тариф: {tier_title(tier)}")
    if rendered is not None:
        text, markup = rendered
        await safe_edit(callback, text, markup)


# ----------------------------------------------------------------------------
# Tier freeze: temporarily pause catalog access for a whole tier
# ----------------------------------------------------------------------------

async def render_freeze(tier_flag_repository: TierFlagRepository) -> tuple[str, InlineKeyboardMarkup]:
    frozen = await tier_flag_repository.frozen_tiers()
    rows: list[list[InlineKeyboardButton]] = []
    for tier in ALL_TIERS:
        is_frozen = tier in frozen
        state = "🚫 заморожено" if is_frozen else "✅ активно"
        rows.append([InlineKeyboardButton(
            text=f"{tier_title(tier)}: {state}",
            callback_data=f"adm:freeze:t:{tier}",
        )])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="adm:home")])
    text = (
        "🧊 <b>Доступ по тарифах</b>\n\n"
        "Натисни тариф, щоб призупинити або відновити доступ до тренувань для його користувачів.\n\n"
        "🚫 заморожено — користувачі цього тарифу тимчасово не бачать тренувань (доступ не згорає).\n"
        "✅ активно — все працює як звичайно."
    )
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "adm:freeze:menu")
async def open_freeze_menu(callback: CallbackQuery, tier_flag_repository: TierFlagRepository, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id if callback.from_user else None):
        await callback.answer("Немає доступу", show_alert=True)
        return
    await state.clear()
    text, markup = await render_freeze(tier_flag_repository)
    await safe_edit(callback, text, markup)
    await callback.answer()


@router.callback_query(F.data.startswith("adm:freeze:t:"))
async def toggle_freeze(callback: CallbackQuery, tier_flag_repository: TierFlagRepository) -> None:
    if not is_admin(callback.from_user.id if callback.from_user else None):
        await callback.answer("Немає доступу", show_alert=True)
        return
    tier = callback.data.removeprefix("adm:freeze:t:")
    if tier not in ALL_TIERS:
        await callback.answer("Невідомий тариф", show_alert=True)
        return
    now_frozen = not await tier_flag_repository.is_frozen(tier)
    await tier_flag_repository.set_frozen(tier, now_frozen)
    await callback.answer(f"{tier_title(tier)}: {'заморожено' if now_frozen else 'активно'}")
    text, markup = await render_freeze(tier_flag_repository)
    await safe_edit(callback, text, markup)


# ----------------------------------------------------------------------------
# Set a user's tier by Telegram id
# ----------------------------------------------------------------------------

def user_tier_picker(telegram_id: int) -> InlineKeyboardMarkup:
    tier_buttons = [
        InlineKeyboardButton(text=tier_title(tier), callback_data=f"adm:utier:set:{telegram_id}:{tier}")
        for tier in ALL_TIERS
    ]
    rows = [
        [InlineKeyboardButton(text=f"❌ {tier_title(TIER_NONE)}", callback_data=f"adm:utier:set:{telegram_id}:{TIER_NONE}")],
        tier_buttons,
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm:home")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "adm:utier:start")
async def user_tier_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id if callback.from_user else None):
        await callback.answer("Немає доступу", show_alert=True)
        return
    await state.set_state(AdminStates.user_tier_id)
    await callback.message.answer(
        "Надішли Telegram ID користувача, якому треба змінити тариф.\n\n"
        "ID — це числовий номер акаунта. Клієнт бачить свій ID, коли пише боту /start."
    )
    await callback.answer()


@router.message(AdminStates.user_tier_id)
async def user_tier_pick(message: Message, state: FSMContext, token_service: TokenService) -> None:
    raw_id = (message.text or "").strip()
    if not raw_id.lstrip("-").isdigit():
        await message.answer("Потрібен числовий Telegram ID. Приклад: 123456789")
        return
    telegram_id = int(raw_id)
    await state.clear()

    access = await token_service.get_active_access(telegram_id)
    current = (
        f"Поточний тариф: <b>{tier_title(access.tier)}</b> (до {access.expires_at.strftime('%d.%m.%Y')})"
        if access else "Поточний тариф: <b>немає</b>"
    )
    await message.answer(
        f"Користувач ID <code>{telegram_id}</code>\n{current}\n\nОбери новий тариф:",
        reply_markup=user_tier_picker(telegram_id),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("adm:utier:set:"))
async def user_tier_set(callback: CallbackQuery, token_service: TokenService) -> None:
    if not is_admin(callback.from_user.id if callback.from_user else None):
        await callback.answer("Немає доступу", show_alert=True)
        return
    # adm:utier:set:<telegram_id>:<tier>
    _, _, _, raw_id, tier = callback.data.split(":")
    telegram_id = int(raw_id)

    try:
        access = await token_service.set_tier(
            telegram_id=telegram_id,
            tier=tier,
            changed_by_tg_id=callback.from_user.id if callback.from_user else None,
        )
    except InvalidTierError:
        await callback.answer("Невідомий тариф", show_alert=True)
        return

    if access is None:
        text = (
            f"✅ Готово.\n\nКористувач ID <code>{telegram_id}</code>: доступ знято "
            f"(тариф <b>{tier_title(TIER_NONE)}</b>). Тренування стануть недоступні одразу."
        )
    else:
        text = (
            f"✅ Готово.\n\nКористувач ID <code>{telegram_id}</code>: тариф <b>{tier_title(access.tier)}</b>, "
            f"діє до <b>{access.expires_at.strftime('%d.%m.%Y')}</b>."
        )
    await notify_tier_changed(telegram_id, access.tier if access else None)
    await callback.answer("Тариф змінено")
    markup = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⬅️ В адмін-панель", callback_data="adm:home"),
    ]])
    await safe_edit(callback, text, markup)


async def safe_edit(callback: CallbackQuery, text: str, markup: InlineKeyboardMarkup) -> None:
    message = callback.message
    if message is None:
        return
    try:
        await message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    except Exception:
        await message.answer(text, reply_markup=markup, parse_mode="HTML")
