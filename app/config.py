from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    DATABASE_URL: str = "mysql+aiomysql://alpaca:alpaca@127.0.0.1:3306/alpaca2"
    SECRET_KEY: str = "change-me"
    DEBUG: bool = True


settings = Settings()
