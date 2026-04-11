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

    # Usage guard — optional, graceful fallback when not set
    upstash_rest_url: str = ""        # Upstash REST API URL for command-count monitoring
    upstash_rest_token: str = ""      # Upstash REST API token
    cloudflare_api_token: str = ""    # Cloudflare API token (for R2 analytics API)
    admin_email: str = ""             # Owner email for admin-only endpoints

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()

# ── Free tier limits ───────────────────────────────────────────────────────────
# Single source of truth for all service limits. Update here if tiers change.
FREE_TIER_LIMITS: dict[str, int] = {
    "supabase_db_bytes":         500 * 1024 * 1024,       # 500 MB
    "r2_storage_bytes":          10 * 1024 * 1024 * 1024,  # 10 GB
    "upstash_commands_per_day":  10_000,
    "upstash_memory_bytes":      256 * 1024 * 1024,        # 256 MB
    "vercel_bandwidth_bytes":    100 * 1024 * 1024 * 1024, # 100 GB
    "sentry_errors_per_month":   5_000,
    "github_actions_min_month":  2_000,
}

ALERT_THRESHOLD_PCT: float = 0.80   # send alert at 80% of any limit
BLOCK_THRESHOLD_PCT: float = 0.90   # block new ingest jobs at 90% of critical limits
ALLOWED_USER_CAP: int = 10          # friends-only hard cap on total registered users
GPU_MONTHLY_BUDGET_USD: float = 25.0  # block GPU jobs if monthly spend exceeds this
