from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    APP_ENV: str = "development"
    APP_NAME: str = "ServerMind"
    APP_VERSION: str = "1.0.0"
    SECRET_KEY: str = "change-me-in-production"
    ENCRYPTION_KEY: str = "change-me-in-production"

    # Background scheduler — must run in exactly ONE process. Set false on extra
    # web workers when scaling horizontally so jobs don't fire multiple times.
    ENABLE_SCHEDULER: bool = True

    # Error monitoring (optional)
    SENTRY_DSN: str = ""

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://servermind:password@localhost:5432/servermind"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Claude API
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-4-20250514"

    # JWT
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Rate limiting (Update 14)
    RATE_LIMIT_ENABLED: bool = True
    LOGIN_RATE_LIMIT: str = "10/minute"     # per IP (2FA login is a 2-request flow)
    REGISTER_RATE_LIMIT: str = "3/minute"   # per IP
    COMMAND_RATE_PER_MIN: int = 30          # per user+server, WebSocket exec (rule 8)

    # WebSocket auth ticket (Update 14.6) — short-lived, single-use
    WS_TICKET_TTL_SECONDS: int = 30

    # 2FA / TOTP (Update 14.3) — per-user failed-attempt lockout on login
    TOTP_MAX_FAILURES: int = 10
    TOTP_LOCKOUT_SECONDS: int = 900

    # Email verification (Update 14.4)
    REQUIRE_EMAIL_VERIFICATION: bool = False
    EMAIL_VERIFICATION_TOKEN_HOURS: int = 24
    APP_BASE_URL: str = ""   # frontend origin for verify links, e.g. https://app.example.com

    # CORS
    ALLOWED_ORIGINS: list[str] = ["http://localhost:5173"]

    # Email
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_FROM: str = "noreply@servermind.ai"

    # Cloudflare R2
    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY: str = ""
    R2_SECRET_KEY: str = ""
    R2_BUCKET: str = "servermind-logs"


settings = Settings()
