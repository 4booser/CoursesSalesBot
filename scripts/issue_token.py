"""Issue a one-time access token by hand.

Use when a buyer paid but lost their access link (or their tier grant), and you
need to hand them a fresh token to activate. Mirrors what the site's
``POST /api/tokens`` endpoint does, but runnable from a shell inside the stack:

    docker compose -f deploy/docker-compose.prod.yml exec bot \
        python -m scripts.issue_token pro

Optional args:
    python -m scripts.issue_token <tier> [--days N] [--payment-id TAG]

The buyer activates it by sending the bot:  /activate <TOKEN>
(or by opening the printed t.me link).
"""

import argparse
import asyncio

from app.config import settings
from app.database.session import session_maker
from app.repositories.payment_event_repository import PaymentEventRepository
from app.repositories.tier_access_repository import TierAccessRepository
from app.repositories.token_repository import TokenRepository
from app.services.token_service import (
    InvalidTierError,
    TokenAlreadyExistsError,
    TokenService,
)
from app.tiers import ALL_TIERS


def telegram_link(raw_token: str) -> str:
    if not settings.BOT_USERNAME:
        return ""
    username = settings.BOT_USERNAME.removeprefix("@")
    return f"https://t.me/{username}?start={raw_token}"


async def main() -> None:
    parser = argparse.ArgumentParser(description="Issue a one-time access token.")
    parser.add_argument("tier", choices=ALL_TIERS, help="Tier to grant (lite / pro / vip).")
    parser.add_argument("--days", type=int, default=None, help="Override access duration in days.")
    parser.add_argument(
        "--payment-id",
        default=None,
        help="Optional tag for traceability. Omit to skip dedup; reusing an existing one is rejected.",
    )
    args = parser.parse_args()

    async with session_maker() as session:
        service = TokenService(
            token_repository=TokenRepository(session),
            tier_access_repository=TierAccessRepository(session),
            payment_event_repository=PaymentEventRepository(session),
        )
        try:
            created = await service.create_token(
                created_by_tg_id=0,
                tier=args.tier,
                payment_id=args.payment_id,
                duration_days=args.days,
            )
        except TokenAlreadyExistsError:
            await session.rollback()
            raise SystemExit(f"A token for payment-id '{args.payment_id}' already exists.")
        except InvalidTierError as error:
            await session.rollback()
            raise SystemExit(str(error))
        await session.commit()

    print("\n✅ Token issued\n")
    print(f"  Tier:     {created.tier}")
    print(f"  Days:     {created.duration_days}")
    print(f"  Token:    {created.raw_token}")
    link = telegram_link(created.raw_token)
    if link:
        print(f"  Link:     {link}")
    print("\nSend the buyer:  /activate " + created.raw_token + "\n")


if __name__ == "__main__":
    asyncio.run(main())
