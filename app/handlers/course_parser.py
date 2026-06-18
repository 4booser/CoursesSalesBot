import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.config import settings
from app.repositories.course_repository import CourseRepository
from app.services.youtube_parser import YoutubeCourseParser, YoutubeParseError, extract_youtube_video_id

router = Router(name=__name__)
logger = logging.getLogger(__name__)


@router.message(Command("parsecourse"))
async def parse_course_command(message: Message, course_repository: CourseRepository) -> None:
    if message.from_user is None or message.from_user.id not in settings.admin_ids:
        await message.answer("Нет доступа.")
        return

    text = message.text or ""
    await parse_youtube_course(message, course_repository, text)


@router.message()
async def parse_course_from_admin_message(message: Message, course_repository: CourseRepository) -> None:
    if message.from_user is None or message.from_user.id not in settings.admin_ids:
        return

    text = message.text or message.caption or ""
    if extract_youtube_video_id(text) is None:
        return

    await parse_youtube_course(message, course_repository, text)


async def parse_youtube_course(message: Message, course_repository: CourseRepository, text: str) -> None:
    parser = YoutubeCourseParser()

    try:
        parsed = await parser.parse(text)
    except YoutubeParseError:
        await message.answer("Не нашёл YouTube-ссылку. Пришли ссылку на видео или /parsecourse <ссылка>.")
        return
    except Exception:
        logger.exception("Failed to parse YouTube course")
        await message.answer("Не получилось открыть видео и прочитать данные. Проверь, что ссылка доступна по URL.")
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
