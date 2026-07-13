import uuid

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    sentinel_l7_base_url: str = "http://localhost:8001"
    entitlement_ttl_seconds: int = 60
    poll_interval_seconds: int = 60
    billing_customer_id: uuid.UUID | None = None
    enable_scheduler: bool = True
    operator_api_token: str
    session_secret_key: str
    stripe_secret_key: str
    stripe_webhook_secret: str
    app_base_url: str = "http://localhost:8000"
    r2_account_id: str
    r2_access_key_id: str
    r2_secret_access_key: str
    r2_bucket_name: str
    resend_api_key: str
    resend_from_email: str


settings = Settings()
