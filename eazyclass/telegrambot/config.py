from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    api_base_url: str
    hmac_secret: str
    bot_token: str
    redis_storage_url: str
    storage_state_ttl: int
    storage_data_ttl: int
    platform: str = "telegram"

    base_link: str = Field(alias="base_scraping_url")

    faculties_cache_file: str = str(BASE_DIR / "cache" / "faculties.json")
    teachers_cache_file: str = str(BASE_DIR / "cache" / "teachers.json")
    update_keyboards_rule: dict = {
        "trigger": "cron",
        "hour": 3,
        "minute": 0,
        "timezone": "Europe/Moscow",
    }

    log_level: str = "INFO"
    project_name: str = "TelegramBot"

    model_config = SettingsConfigDict(
        env_prefix="TELEGRAM_",
        env_file=BASE_DIR.parent.parent / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Игнорировать лишние поля в .env
    )


settings = Settings()

if __name__ == "__main__":
    print(settings.model_config["env_file"])
    print(settings.hmac_secret)
    print(settings.api_base_url)
    print(settings.base_link)
