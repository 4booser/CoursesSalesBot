"""Token activation: a buyer arrives from the site via a deep link and gets a tier."""

import logging

from aiogram import Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message

from app.services.catalog_service import CatalogService
from app.services.token_service import ActivatedAccess, TokenService
from app.handlers.user_catalog import render_home
from app.tiers import tier_title

router = Router(name=__name__)
logger = logging.getLogger(__name__)


async def grant_and_show(
    message: Message,
    activated: ActivatedAccess,
    token_service: TokenService,
    catalog_service: CatalogService,
) -> None:
    await message.answer(
        "✅ Доступ активовано!\n\n"
        f"Тариф: <b>{tier_title(activated.tier)}</b>\n"
        f"Діє до: <b>{activated.expires_at.strftime('%d.%m.%Y')}</b>\n\n"
        "Ось твої тренування:",
        parse_mode="HTML",
    )
    if message.from_user is None:
        return
    rendered = await render_home(message.from_user.id, token_service, catalog_service)
    if rendered is not None:
        text, markup = rendered
        await message.answer(text, reply_markup=markup, parse_mode="HTML")


@router.message(CommandStart(deep_link=True))
async def start_with_token_handler(
    message: Message,
    command: CommandObject,
    token_service: TokenService,
    catalog_service: CatalogService,
) -> None:
    if message.from_user is None:
        return

    activated = await token_service.activate_token(
        raw_token=command.args or "",
        used_by_tg_id=message.from_user.id,
    )

    if activated is None:
        # Token invalid/used — but the user may already have active access.
        rendered = await render_home(message.from_user.id, token_service, catalog_service)
        if rendered is not None:
            text, markup = rendered
            await message.answer(
                "Це посилання вже використане або недійсне, але доступ у тебе активний 👇",
            )
            await message.answer(text, reply_markup=markup, parse_mode="HTML")
            return
        await message.answer(
            "Посилання недійсне або вже використане. "
            "Перевір, що скопіював його повністю, або звернись до тренера."
        )
        return

    await grant_and_show(message, activated, token_service, catalog_service)


@router.message(Command("activate"))
async def activate_token_handler(
    message: Message,
    command: CommandObject,
    token_service: TokenService,
    catalog_service: CatalogService,
) -> None:
    if message.from_user is None:
        return

    raw_token = (command.args or "").strip()
    if not raw_token:
        await message.answer("Використання: /activate TOKEN")
        return

    activated = await token_service.activate_token(
        raw_token=raw_token,
        used_by_tg_id=message.from_user.id,
    )

    if activated is None:
        await message.answer("Токен не знайдено або вже використано.")
        return

    await grant_and_show(message, activated, token_service, catalog_service)
