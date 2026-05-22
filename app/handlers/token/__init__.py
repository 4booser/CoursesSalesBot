from aiogram import Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message

from app.config import settings
from app.services.token_service import CoursesNotFoundError, TokenAlreadyExistsError, TokenService


router = Router(name=__name__)


def parse_course_ids(raw_args: str | None) -> list[str]:
    if not raw_args:
        return ["default"]

    return [course_id.strip() for course_id in raw_args.replace(",", " ").split() if course_id.strip()]


def format_course_ids(course_ids: list[str]) -> str:
    return "\n".join(f"{index}. {course_id}" for index, course_id in enumerate(course_ids, start=1))


@router.message(Command("token"))
async def create_token_handler(
    message: Message,
    command: CommandObject,
    token_service: TokenService,
) -> None:
    if message.from_user is None:
        await message.answer("Не удалось определить пользователя.")
        return

    telegram_id = message.from_user.id

    if telegram_id not in settings.admin_ids:
        await message.answer("Нет доступа.")
        return

    course_ids = parse_course_ids(command.args)

    try:
        created_token = await token_service.create_token(
            created_by_tg_id=telegram_id,
            course_ids=course_ids,
        )
    except ValueError:
        await message.answer("Укажи корректные course_id: /token python-backend csharp-aspnet")
        return
    except CoursesNotFoundError as error:
        await message.answer(f"Курсы не найдены или выключены: {', '.join(error.course_ids)}")
        return
    except TokenAlreadyExistsError:
        await message.answer("Токен для этого платежа уже существует.")
        return

    await message.answer(
        "Токен создан.\n\n"
        f"Курсы:\n{format_course_ids(created_token.course_ids)}\n\n"
        f"Токен: {created_token.raw_token}\n\n"
        "Сохрани его сейчас. В базе хранится только hash, сырой токен потом восстановить нельзя.\n\n"
        f"ID: {created_token.token_id}\n"
        f"Preview: {created_token.token_preview}"
    )


@router.message(CommandStart(deep_link=True))
async def start_with_token_handler(
    message: Message,
    command: CommandObject,
    token_service: TokenService,
) -> None:
    if message.from_user is None:
        await message.answer("Не удалось определить пользователя.")
        return

    raw_token = command.args or ""
    activated_token = await token_service.activate_token(
        raw_token=raw_token,
        used_by_tg_id=message.from_user.id,
    )

    if activated_token is None:
        await message.answer("Токен не найден или уже был использован. Проверь, что ссылка скопирована полностью.")
        return

    await message.answer("Доступ активирован.\n\n" f"Курсы:\n{format_course_ids(activated_token.course_ids)}")


@router.message(CommandStart())
async def start_handler(message: Message) -> None:
    await message.answer(
        "Привет. После оплаты на сайте ты получишь ссылку на этого бота. "
        "Открой её, и я активирую доступ к курсу.\n\n"
        "Команды:\n"
        "/activate TOKEN — активировать токен вручную\n"
        "/mycourses — посмотреть мои курсы"
    )


@router.message(Command("activate"))
async def activate_token_handler(
    message: Message,
    command: CommandObject,
    token_service: TokenService,
) -> None:
    if message.from_user is None:
        await message.answer("Не удалось определить пользователя.")
        return

    raw_token = command.args or ""

    if not raw_token.strip():
        await message.answer("Использование: /activate TOKEN")
        return

    activated_token = await token_service.activate_token(
        raw_token=raw_token,
        used_by_tg_id=message.from_user.id,
    )

    if activated_token is None:
        await message.answer("Токен не найден или уже был использован.")
        return

    await message.answer("Доступ активирован.\n\n" f"Курсы:\n{format_course_ids(activated_token.course_ids)}")


@router.message(Command("mycourses"))
async def my_courses_handler(
    message: Message,
    token_service: TokenService,
) -> None:
    if message.from_user is None:
        await message.answer("Не удалось определить пользователя.")
        return

    courses = await token_service.get_user_courses(message.from_user.id)

    if not courses:
        await message.answer("У тебя пока нет активированных курсов.")
        return

    await message.answer("Твои курсы:\n\n" + format_course_ids(courses))


@router.message(Command("help"))
async def help_handler(message: Message) -> None:
    await message.answer(
        "Команды:\n"
        "/start — описание бота\n"
        "/activate TOKEN — активировать токен вручную\n"
        "/mycourses — посмотреть активированные курсы\n\n"
        "После оплаты лучше открывать ссылку с сайта — токен активируется автоматически."
    )
