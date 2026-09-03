from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./student_agent.db"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"

    jwt_secret: str = "changeme"
    jwt_algorithm: str = "HS256"
    staff_token_expire_minutes: int = 15
    student_token_expire_minutes: int = 30

    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_verify_token: str = ""
    whatsapp_app_secret: str = ""

    environment: str = "development"


settings = Settings()
