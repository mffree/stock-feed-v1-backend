from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # .env may hold vars for features not wired up yet (JWT_SECRET, APPLE_BUNDLE_ID).
        extra="ignore",
        # Never echo secret values in validation errors / logs.
        hide_input_in_errors=True,
    )

    alpaca_api_key_id: str
    alpaca_secret_key: str
    # Render's Postgres URL (postgres:// or postgresql://). Normalized for
    # asyncpg in app/db.py; don't hand-edit the driver into .env.
    database_url: str


settings = Settings()
