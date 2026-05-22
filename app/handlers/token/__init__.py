from aiogram import Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message

from app.config import settings
from app.services.token_service import TokenAlreadyExistsError, TokenService


router = Router(name=__name__)


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

    course_id = command.args.strip() if command.args else "default"

    try:
        created_token = await token_service.create_token(
            created_by_tg_id=telegram_id,
            course_id=course_id,
        )
    except ValueError:
        await message.answer("Укажи корректный course_id: /token python-backend")
        return
    except TokenAlreadyExistsError:
        await message.answer("Токен для этого платежа уже существует.")
        return

    await message.answer(
        "Токен создан.\n\n"
        f"Курс: <code>{created_token.course_id}</code>\n"
        f"Токен: <code>{created_token.raw_token}</code>\n\n"
        "Сохрани его сейчас. В базе хранится только hash, "
        "сырой токен потом восстановить нельзя.\n\n"
        f"ID: <code>{created_token.token_id}</code>\n"
        f"Preview: <code>{created_token.token_preview}</code>",
        parse_mode="HTML",
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
        await message.answer(
            "Токен не найден или уже был использован. "
            "Проверь, что ссылка скопирована полностью."
        )
        return

    await message.answer(
        "Доступ активирован.\n\n"
        f"Курс: <code>{activated_token.course_id}</code>",
        parse_mode="HTML",
    )


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

    await message.answer(
        "Доступ активирован.\n\n"
        f"Курс: <code>{activated_token.course_id}</code>",
        parse_mode="HTML",
    )


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

    courses_text = "\n".join(
        f"{index}. <code>{course_id}</code>"
        for index, course_id in enumerate(courses, start=1)
    )

    await message.answer(
        "Твои курсы:\n\n" + courses_text,
        parse_mode="HTML",
    )


@router.message(Command("help"))
async def help_handler(message: Message) -> None:
    await message.answer(
        "Команды:\n"
        "/start — описание бота\n"
        "/activate TOKEN — активировать токен вручную\n"
        "/mycourses — посмотреть активированные курсы\n\n"
        "После оплаты лучше открывать ссылку с сайта — токен активируется автоматически."
    )
