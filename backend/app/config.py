from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="DT_", extra="ignore")

    # 默认连接本机 PostgreSQL，可用环境变量 DATABASE_URL / DT_DATABASE_URL 覆盖
    database_url: str = "postgresql+psycopg://downtime:downtime@localhost:5432/downtime"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    seed_on_startup: bool = True


settings = Settings()
