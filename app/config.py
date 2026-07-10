from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    sentinel_l7_base_url: str = "http://localhost:8001"
    entitlement_ttl_seconds: int = 60


settings = Settings()
