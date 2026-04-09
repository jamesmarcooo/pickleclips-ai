from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    supabase_url: str
    supabase_anon_key: str
    supabase_jwt_secret: str
    r2_account_id: str
    r2_access_key_id: str
    r2_secret_access_key: str
    r2_bucket_name: str
    redis_url: str = "redis://localhost:6379/0"
    environment: str = "development"
    app_base_url: str = "http://localhost:3000"
    tracknetv2_weights_path: str | None = None  # path to TrackNetV2 weights on GPU instance

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
