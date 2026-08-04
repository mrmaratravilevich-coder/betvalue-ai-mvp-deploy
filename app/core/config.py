"""
Централизованная конфигурация приложения.
Значения читаются из переменных окружения / .env — см. .env.example.
"""
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Общие
    APP_NAME: str = "BetValue AI"
    ENV: str = "development"
    DEBUG: bool = True
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # База данных
    DATABASE_URL: str = "postgresql+asyncpg://betvalue:betvalue@localhost:5432/betvalue"
    AUTO_CREATE_SCHEMA: bool = False
    AUTO_SYNC_MATCHES: bool = True
    MATCH_SYNC_INTERVAL_SECONDS: int = 60 * 60 * 6

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        """Render and similar hosts provide a sync PostgreSQL URL."""
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+asyncpg://", 1)
        if value.startswith("postgresql://") and "+asyncpg" not in value:
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        return value

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip().rstrip("/") for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    # Redis / Celery
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"
    # Тот же оффсет, что и в Татарстане (UTC+3), где базируется STZ16 —
    # время в разделе "Ежедневный цикл" ТЗ ("06:00" и т.п.) имеет смысл
    # только в местном времени, не в UTC контейнера.
    CELERY_TIMEZONE: str = "Europe/Moscow"

    # Auth
    JWT_SECRET_KEY: str = "CHANGE_ME_IN_PRODUCTION"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12

    # Источники данных (открытые на старте; агрегатор коэффициентов подключается позже)
    FOOTBALL_DATA_API_KEY: str | None = None
    FOOTBALL_DATA_BASE_URL: str = "https://api.football-data.org/v4"
    API_SPORTS_KEY: str | None = None
    API_SPORTS_HOCKEY_BASE_URL: str = "https://v1.hockey.api-sports.io"
    API_SPORTS_BASKETBALL_BASE_URL: str = "https://v1.basketball.api-sports.io"
    API_TENNIS_KEY: str | None = None
    API_TENNIS_BASE_URL: str = "https://api.api-tennis.com/tennis/"
    STATSBOMB_OPEN_DATA: bool = True
    # Betfair Exchange API: Delayed App Key бесплатен (для чтения котировок он и не должен
    # переставать быть free — Live-ключ с активационным сбором нужен только для реальных ставок,
    # что нам не требуется). https://identitysso.betfair.com — логин, https://api.betfair.com — данные.
    BETFAIR_APP_KEY: str | None = None
    BETFAIR_USERNAME: str | None = None
    BETFAIR_PASSWORD: str | None = None
    BETFAIR_SESSION_TOKEN: str | None = None
    BETFAIR_LOGIN_URL: str = "https://identitysso.betfair.com/api/login"
    BETFAIR_KEEPALIVE_URL: str = "https://identitysso.betfair.com/api/keepAlive"
    BETFAIR_API_URL: str = "https://api.betfair.com/exchange/betting/json-rpc/v1"

    # Бизнес-правила (значения по умолчанию, переопределяются в UserSettings)
    MIN_EV_THRESHOLD: float = 0.05
    MAX_ODDS: float = 6.0
    MIN_HISTORICAL_MATCHES: int = 1000
    DEFAULT_KELLY_FRACTION: float = 0.25

    # Telegram
    TELEGRAM_BOT_TOKEN: str | None = None
    TELEGRAM_WEBHOOK_SECRET: str | None = None
    TELEGRAM_CHANNEL_URL: str | None = None
    TELEGRAM_WEB_APP_URL: str | None = None

    # Affiliate integration (disabled until a signed agreement is in place)
    AFFILIATE_ENABLED: bool = False
    AFFILIATE_PROVIDER: str = "partner"
    AFFILIATE_BASE_URL: str | None = None
    AFFILIATE_ALLOWED_HOSTS: str = ""
    AFFILIATE_PROMO_CODE: str | None = None
    AFFILIATE_PROMO_PARAM: str = "promo_code"
    AFFILIATE_CLICK_ID_PARAM: str = "click_id"
    AFFILIATE_SUB_PARAM_PREFIX: str = "sub"

    @property
    def affiliate_allowed_hosts(self) -> set[str]:
        return {
            host.strip().lower()
            for host in self.AFFILIATE_ALLOWED_HOSTS.split(",")
            if host.strip()
        }

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
