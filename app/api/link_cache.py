import redis.asyncio as redis


class PurchaseLinkStore:
    """Хранит готовую персональную telegram-ссылку покупки во временном кэше.

    Raw token невосстановим (в БД только его hash), поэтому сразу после
    создания токена мы кладём готовый telegram_link в Redis по reference
    платежа. Страница "спасибо" сайта потом забирает его оттуда.
    """

    KEY_PREFIX = "purchase-link:"
    DEFAULT_TTL_SECONDS = 86400  # 24h — столько же живёт инвойс Mono

    def __init__(self, redis_url: str):
        self.client = redis.from_url(redis_url, decode_responses=True)

    def _key(self, reference: str) -> str:
        return self.KEY_PREFIX + reference.strip()

    async def save(self, reference: str, telegram_link: str, ttl_seconds: int | None = None) -> None:
        if not reference.strip() or not telegram_link:
            return
        await self.client.set(
            self._key(reference),
            telegram_link,
            ex=ttl_seconds or self.DEFAULT_TTL_SECONDS,
        )

    async def get(self, reference: str) -> str | None:
        if not reference.strip():
            return None
        return await self.client.get(self._key(reference))

    async def close(self) -> None:
        await self.client.aclose()
