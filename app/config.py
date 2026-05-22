from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    BOT_TOKEN: str
    DATABASE_URL: str
    ADMIN_IDS: str = ""

    SITE_API_KEY: str = ""
    API_TOKEN: str = ""
    BOT_USERNAME: str = ""

    POSTGRES_DB: str = "bot_db"
    POSTGRES_USER: str = "bot_user"
    POSTGRES_PASSWORD: str = "bot_password"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def admin_ids(self) -> set[int]:
        if not self.ADMIN_IDS.strip():
            return set()

        return {
            int(admin_id.strip())
            for admin_id in self.ADMIN_IDS.split(",")
            if admin_id.strip()
        }

    @property
    def site_api_key(self) -> str:
        return self.SITE_API_KEY or self.API_TOKEN


settings = Settings()
