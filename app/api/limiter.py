import time

import redis.asyncio as redis
from fastapi import HTTPException, status


class RedisRateLimiter:
    def __init__(self, redis_url: str, limit: int, window_seconds: int):
        self.limit = limit
        self.window_seconds = window_seconds
        self.client = redis.from_url(redis_url, decode_responses=True)

    async def check(self, key: str) -> None:
        now = int(time.time())
        window = now // self.window_seconds
        redis_key = "rate-limit:" + key + ":" + str(window)

        current = await self.client.incr(redis_key)
        if current == 1:
            await self.client.expire(redis_key, self.window_seconds + 1)

        if current > self.limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests",
            )

    async def close(self) -> None:
        await self.client.aclose()
