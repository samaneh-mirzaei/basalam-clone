from functools import lru_cache

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BASALAM_", env_file=".env", extra="ignore")
    database_url: SecretStr
    jwt_secret: SecretStr | None = None
    jwt_issuer: str = "basalam"
    jwt_audience: str = "basalam-api"
    access_token_minutes: int = 60

    @field_validator("database_url")
    @classmethod
    def configured_postgres(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        if "replace-me" in raw:
            raise ValueError("Configure BASALAM_DATABASE_URL before using database routes.")
        try:
            url = make_url(raw)
        except ValueError as exc:
            raise ValueError("BASALAM_DATABASE_URL must be a valid PostgreSQL URL.") from exc
        if url.drivername != "postgresql+psycopg" or not url.database:
            raise ValueError("BASALAM_DATABASE_URL must use postgresql+psycopg and name a database.")
        return value


@lru_cache
def settings() -> Settings:
    return Settings()
