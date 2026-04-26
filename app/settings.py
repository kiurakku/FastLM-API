from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    redis_url: str = "redis://localhost:6379/0"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    admin_secret: str
    webhook_hmac_secret: str = "dev-change-me"
    enabled_plugins: str = "audit,pii_mask,prompt_injection,cost_limit"
    default_monthly_token_budget: int = 1_000_000
    requests_per_minute: int = 60
    api_title: str = "FastLM API"


settings = Settings()
