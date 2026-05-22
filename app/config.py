from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    BOT_TOKEN: str
    DATABASE_URL: str
    ADMIN_IDS: str = ""
    SITE_API_KEY: str = ""
    BOT_USERNAME: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
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


settings = Settings()
