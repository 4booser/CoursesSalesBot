"""Helpers to capture an uploaded file from a Telegram message and to resend it.

Files are stored by Telegram ``file_id`` — the owner uploads any file in the admin
panel, we persist its id + metadata, and later deliver it with the matching
``answer_*`` method. ``media_type`` records which method to use.
"""

from dataclasses import dataclass

from aiogram.types import InlineKeyboardMarkup, Message

from app.database.models import Attachment

# media_type values, one per supported Telegram file kind.
MEDIA_DOCUMENT = "document"
MEDIA_PHOTO = "photo"
MEDIA_VIDEO = "video"
MEDIA_AUDIO = "audio"
MEDIA_VOICE = "voice"
MEDIA_ANIMATION = "animation"

_MEDIA_ICONS = {
    MEDIA_DOCUMENT: "📄",
    MEDIA_PHOTO: "🖼",
    MEDIA_VIDEO: "🎞",
    MEDIA_AUDIO: "🎵",
    MEDIA_VOICE: "🎤",
    MEDIA_ANIMATION: "🎬",
}

_DEFAULT_TITLES = {
    MEDIA_DOCUMENT: "Документ",
    MEDIA_PHOTO: "Зображення",
    MEDIA_VIDEO: "Відео",
    MEDIA_AUDIO: "Аудіо",
    MEDIA_VOICE: "Голосове",
    MEDIA_ANIMATION: "GIF",
}


@dataclass
class ExtractedFile:
    media_type: str
    file_id: str
    file_unique_id: str | None
    file_name: str | None
    mime_type: str | None
    file_size: int | None
    title: str


def media_icon(media_type: str) -> str:
    return _MEDIA_ICONS.get(media_type, "📎")


def extract_file(message: Message) -> ExtractedFile | None:
    """Pull the first supported file out of an incoming message, or ``None``.

    The display title prefers the message caption, then the original file name,
    then a generic per-type label.
    """
    caption = (message.caption or "").strip()

    if message.document:
        d = message.document
        return _build(MEDIA_DOCUMENT, d.file_id, d.file_unique_id, d.file_name, d.mime_type, d.file_size, caption)
    if message.video:
        v = message.video
        return _build(MEDIA_VIDEO, v.file_id, v.file_unique_id, v.file_name, v.mime_type, v.file_size, caption)
    if message.animation:
        a = message.animation
        return _build(MEDIA_ANIMATION, a.file_id, a.file_unique_id, a.file_name, a.mime_type, a.file_size, caption)
    if message.audio:
        au = message.audio
        name = au.file_name or au.title
        return _build(MEDIA_AUDIO, au.file_id, au.file_unique_id, name, au.mime_type, au.file_size, caption)
    if message.voice:
        vo = message.voice
        return _build(MEDIA_VOICE, vo.file_id, vo.file_unique_id, None, vo.mime_type, vo.file_size, caption)
    if message.photo:
        p = message.photo[-1]  # largest size
        return _build(MEDIA_PHOTO, p.file_id, p.file_unique_id, None, None, p.file_size, caption)
    return None


def _build(
    media_type: str,
    file_id: str,
    file_unique_id: str | None,
    file_name: str | None,
    mime_type: str | None,
    file_size: int | None,
    caption: str,
) -> ExtractedFile:
    title = caption or (file_name or "").strip() or _DEFAULT_TITLES.get(media_type, "Файл")
    return ExtractedFile(
        media_type=media_type,
        file_id=file_id,
        file_unique_id=file_unique_id,
        file_name=file_name,
        mime_type=mime_type,
        file_size=file_size,
        title=title[:256],
    )


def human_size(size: int | None) -> str:
    if not size:
        return "—"
    value = float(size)
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if value < 1024 or unit == "ГБ":
            return f"{value:.0f} {unit}" if unit == "Б" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} ГБ"


async def send_attachment(
    message: Message,
    attachment: Attachment,
    caption: str | None = None,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Deliver an attachment to the chat using the method for its media type."""
    kwargs = {"caption": caption, "reply_markup": reply_markup, "parse_mode": "HTML"}
    file_id = attachment.file_id
    if attachment.media_type == MEDIA_PHOTO:
        await message.answer_photo(file_id, **kwargs)
    elif attachment.media_type == MEDIA_VIDEO:
        await message.answer_video(file_id, **kwargs)
    elif attachment.media_type == MEDIA_AUDIO:
        await message.answer_audio(file_id, **kwargs)
    elif attachment.media_type == MEDIA_VOICE:
        await message.answer_voice(file_id, **kwargs)
    elif attachment.media_type == MEDIA_ANIMATION:
        await message.answer_animation(file_id, **kwargs)
    else:
        await message.answer_document(file_id, **kwargs)
