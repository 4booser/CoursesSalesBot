from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.config import settings
from app.services.token_service import TokenService


router = Router(name="token")


@router.message(Command("token"))
async def create_token_handler(
    message: Message,
    token_service: TokenService,
) -> None:
    if message.from_user is None:
        await message.answer("Не удалось определить пользователя.")
        return

    telegram_id = message.from_user.id

    if telegram_id not in settings.admin_ids:
        await message.answer("Нет доступа.")
        return

    created_token = await token_service.create_token(
        created_by_tg_id=telegram_id,
    )

    await message.answer(
        "Токен создан.\n\n"
        f"<code>{created_token.raw_token}</code>\n\n"
        "Сохрани его сейчас. В базе хранится только hash, "
        "сырой токен потом восстановить нельзя.\n\n"
        f"ID: <code>{created_token.token_id}</code>\n"
        f"Preview: <code>{created_token.token_preview}</code>",
        parse_mode="HTML",
    )