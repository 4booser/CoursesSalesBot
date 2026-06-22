import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.config import settings
from app.repositories.course_repository import CourseRepository
from app.services.youtube_parser import (
    YoutubeCourseParser,
    YoutubeLinkNotFoundError,
    YoutubeParseError,
    extract_youtube_video_id,
)

router = Router(name=__name__)
logger = logging.getLogger(__name__)


@router.message(Command("add_course"))
async def add_course_command(message: Message, course_repository: CourseRepository) -> None:
    if message.from_user is None or message.from_user.id not in settings.admin_ids:
        await message.answer("Нет доступа.")
        return

    text = message.text or ""
    await import_youtube_course(message, course_repository, text)


@router.message()
async def import_youtube_course_from_admin_message(message: Message, course_repository: CourseRepository) -> None:
    if message.from_user is None or message.from_user.id not in settings.admin_ids:
        return

    text = message.text or message.caption or ""
    if extract_youtube_video_id(text) is None:
        return

    await import_youtube_course(message, course_repository, text)


async def import_youtube_course(message: Message, course_repository: CourseRepository, text: str) -> None:
    parser = YoutubeCourseParser(cookies_file=settings.YOUTUBE_COOKIES_FILE or None)

    try:
        parsed = await parser.parse(text)
    except YoutubeLinkNotFoundError:
        await message.answer("Не нашёл YouTube-ссылку. Пришли ссылку на видео или /add_course <ссылка>.")
        return
    except YoutubeParseError as error:
        logger.warning("Failed to import YouTube course: %s", error)
        await message.answer(
            "Не получилось открыть видео и прочитать данные. "
            "Для видео «доступ по ссылке» достаточно ссылки; для полностью приватного видео "
            "нужен YOUTUBE_COOKIES_FILE с доступом к аккаунту."
        )
        return
    except Exception:
        logger.exception("Unexpected YouTube course import error")
        await message.answer("Неожиданная ошибка при импорте курса из YouTube.")
        return

    course_id = f"yt-{parsed.video_id}"
    await course_repository.upsert(
        course_id=course_id,
        title=parsed.title,
        description=parsed.description,
        invite_link=parsed.url,
        thumbnail_url=parsed.thumbnail_url,
        youtube_url=parsed.url,
        is_active=True,
    )

    await message.answer(
        "Курс сохранён из YouTube.\n\n"
        f"ID: {course_id}\n"
        f"Название: {parsed.title}\n"
        f"Видео: {parsed.url}\n"
        f"Превью: {parsed.thumbnail_url or 'не найдено'}"
    )
