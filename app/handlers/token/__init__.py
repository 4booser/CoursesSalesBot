from aiogram import Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message

from app.config import settings
from app.services.token_service import TokenService


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

    created_token = await token_service.create_token(
        created_by_tg_id=telegram_id,
        course_id=course_id,
    )

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
        "Открой её, и я активирую доступ к курсу."
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
