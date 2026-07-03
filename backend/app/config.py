from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    APP_ENV: str = "development"
    APP_NAME: str = "ServerAlly"
    APP_VERSION: str = "1.0.0"
    SECRET_KEY: str = "change-me-in-production"
    ENCRYPTION_KEY: str = "change-me-in-production"

    # Background scheduler — must run in exactly ONE process. Set false on extra
    # web workers when scaling horizontally so jobs don't fire multiple times.
    ENABLE_SCHEDULER: bool = True

    # Error monitoring (optional)
    SENTRY_DSN: str = ""

    # Plan-limits wall (docs/AI-METERING.md + PRICING-FREE-VS-PRO.md). The pricing
    # model is "open features, two meters": every feature is available on every plan;
    # only the Ally-action allowance and the server cap differ. The ai_usage ledger
    # ALWAYS records; this flag only controls whether the two meters actually block
    # when exhausted. Off by default: dev and self-hosted instances just collect
    # data; the cloud deployment turns it on.
    ENFORCE_PLAN_LIMITS: bool = False

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://servermind:password@localhost:5432/servermind"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Claude API
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-5"

    # AI provider (Update 20 — multi-provider, bring-your-own-key). AI_PROVIDER picks
    # the brain: 'anthropic' | 'openai' | 'gemini' | 'openai_compatible'.
    # AI_API_KEY / AI_MODEL / AI_BASE_URL configure it; empty values fall back to the
    # ANTHROPIC_* settings above, so existing setups keep working unchanged.
    AI_PROVIDER: str = "anthropic"
    AI_API_KEY: str = ""
    AI_MODEL: str = ""
    AI_BASE_URL: str = ""
    # Hosted "ServerAlly AI" subscription (Update 20.3) — for customers without their
    # own key. When AI_PROVIDER='servermind', AI_API_KEY is the subscription token and
    # requests go to this gateway (which holds our upstream key + meters usage).
    AI_GATEWAY_URL: str = "https://ai.serverally.app/v1"

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

    # Hosting-panel TLS verification. Off by default because panels commonly use
    # self-signed certs; operators whose panels have valid certs can enable it.
    HOSTING_TLS_VERIFY: bool = False

    # Execution backend — "celery" (durable worker: installs keep running if the
    # window closes and can be rejoined) or "inline" (in the web process). When set
    # to "celery" but no worker is responding, execution safely falls back to inline,
    # so this is safe to default on. (Update 17 — Background Tasks)
    EXECUTION_BACKEND: str = "celery"
    EXECUTION_LOG_TTL: int = 3600   # seconds to retain a run's streamed output for replay/reconnect

    # Interactive-execution safety (Update 16, Phase A) — a streamed command that
    # produces no output for this long is treated as stuck (likely waiting for input
    # it can't get) and stopped with a clear message; the hard ceiling bounds total run time.
    SSH_IDLE_TIMEOUT_SECONDS: int = 300
    SSH_MAX_RUNTIME_SECONDS: int = 3600

    # CORS
    ALLOWED_ORIGINS: list[str] = ["http://localhost:5173"]

    # Email
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_FROM: str = "noreply@serverally.ai"

    # Cloudflare R2
    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY: str = ""
    R2_SECRET_KEY: str = ""
    R2_BUCKET: str = "serverally-logs"


settings = Settings()
