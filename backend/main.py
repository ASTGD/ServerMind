import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import settings
from app.database import AsyncSessionLocal
from app.routers import assistant as assistant_router
from app.routers import audit as audit_router
from app.routers import auth as auth_router
from app.routers import backups as backups_router
from app.routers import cloud_accounts as cloud_accounts_router
from app.routers import commands as commands_router
from app.routers import dev as dev_router
from app.routers import files as files_router
from app.routers import fleet as fleet_router
from app.routers import hosting as hosting_router
from app.routers import installed as installed_router
from app.routers import missions as missions_router
from app.routers import monitoring as monitoring_router
from app.routers import notifications as notifications_router
from app.routers import server_reports as server_reports_router
from app.routers import playbooks as playbooks_router
from app.routers import rdp as rdp_router
from app.routers import recipes as recipes_router
from app.routers import scheduler as scheduler_router
from app.routers import scripts as scripts_router
from app.routers import security as security_router
from app.routers import servers as servers_router
from app.routers import settings as settings_router
from app.routers import entitlements as entitlements_router
from app.routers import memories as memories_router
from app.routers import team as team_router
from app.routers import usage as usage_router
from app.services import backup_service, playbook_service, scheduler_service
from app.services.rate_limit_service import limiter
from app.websocket import terminal as ws_handlers
from app.websocket import rdp_tunnel as ws_rdp
from app.workers import metrics_worker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# Error monitoring — only active when a DSN is configured.
if settings.SENTRY_DSN:
    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.APP_ENV,
            release=settings.APP_VERSION,
            traces_sample_rate=0.1,
        )
        logger.info("Sentry initialised (env=%s)", settings.APP_ENV)
    except Exception as exc:  # noqa: BLE001 — never let monitoring break startup
        logger.warning("Sentry init failed: %s", exc)

# In production, hide the interactive API docs.
_is_prod = settings.APP_ENV == "production"

# Refuse to start in production with placeholder/weak secrets.
if _is_prod:
    _weak = "change-me-in-production"
    _problems: list[str] = []
    if settings.SECRET_KEY == _weak or len(settings.SECRET_KEY) < 32:
        _problems.append("SECRET_KEY is default or too short (need >= 32 chars)")
    if settings.ENCRYPTION_KEY == _weak or len(settings.ENCRYPTION_KEY) < 64:
        _problems.append("ENCRYPTION_KEY is default or too short (need 64 hex chars)")
    if "*" in settings.ALLOWED_ORIGINS:
        _problems.append("ALLOWED_ORIGINS='*' is unsafe with credentials — set explicit origins")
    if _problems:
        raise RuntimeError(
            "Refusing to start in production due to insecure config: " + "; ".join(_problems)
        )

app = FastAPI(
    title=settings.APP_NAME,
    description="AI-powered server management platform",
    version=settings.APP_VERSION,
    docs_url=None if _is_prod else "/docs",
    redoc_url=None if _is_prod else "/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting (slowapi) — brute-force protection on auth endpoints.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)


app.include_router(auth_router.router)
app.include_router(audit_router.router)
app.include_router(assistant_router.router)
app.include_router(servers_router.router)
app.include_router(commands_router.router)
app.include_router(dev_router.router)
app.include_router(playbooks_router.router)
app.include_router(recipes_router.router)
app.include_router(scripts_router.router)
app.include_router(scheduler_router.router)
app.include_router(monitoring_router.router)
app.include_router(missions_router.router)
app.include_router(server_reports_router.router)
app.include_router(fleet_router.router)
app.include_router(notifications_router.router)
app.include_router(files_router.router)
app.include_router(security_router.router)
app.include_router(backups_router.router)
app.include_router(team_router.router)
app.include_router(settings_router.router)
app.include_router(hosting_router.router)
app.include_router(installed_router.router)
app.include_router(usage_router.router)
app.include_router(cloud_accounts_router.router)
app.include_router(rdp_router.router)
app.include_router(memories_router.router)
app.include_router(entitlements_router.router)
app.include_router(ws_handlers.router)
app.include_router(ws_rdp.router)  # /ws/rdp — live Remote Desktop via guacd


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "app": settings.APP_NAME}


@app.on_event("startup")
async def on_startup() -> None:
    """Run on application startup."""
    logger.info("ServerAlly backend starting up...")
    # Any mission left "running" from a previous process is orphaned by this restart —
    # mark it resumable (Ally Missions Phase 3).
    from app.services import mission_service
    await mission_service.recover_orphaned()
    async with AsyncSessionLocal() as db:
        await playbook_service.seed_if_empty(db)
        # Apply the saved AI provider config (Settings UI) over the .env default.
        from app.services import llm_service, settings_service
        try:
            ai_cfg = await settings_service.get_ai_config(db)
            if ai_cfg and ai_cfg.get("api_key"):
                llm_service.set_runtime_config(
                    ai_cfg["provider"], ai_cfg["api_key"], ai_cfg["model"], ai_cfg["base_url"]
                )
                logger.info("Loaded AI provider from settings: %s", ai_cfg["provider"])
        except Exception as exc:  # noqa: BLE001 — never block startup on settings
            logger.warning("Could not load AI settings: %s", exc)

    # The scheduler/metrics jobs must run in exactly ONE process. When scaling
    # web workers horizontally, set ENABLE_SCHEDULER=false on the extra workers
    # (and run a single dedicated process with it enabled).
    if not settings.ENABLE_SCHEDULER:
        logger.info("Scheduler disabled on this worker (ENABLE_SCHEDULER=false)")
        return

    # Start APScheduler, load saved tasks, and register metrics collection
    scheduler_service.start()
    await scheduler_service.load_all_tasks()
    await backup_service.load_all_backups()
    # Collect metrics every 5 minutes
    from apscheduler.triggers.interval import IntervalTrigger
    scheduler_service.get_scheduler().add_job(
        metrics_worker.collect_all_metrics,
        trigger=IntervalTrigger(minutes=5),
        id="metrics_collection",
        replace_existing=True,
    )
    logger.info("Metrics collection job registered (every 5 min)")

    # Proactive threat monitoring — read-only IOC scan of every SSH server, alerting
    # the owner when a server newly looks compromised. Heavier than metrics, so
    # every 12h rather than every 5 min.
    from app.workers import threat_worker
    scheduler_service.get_scheduler().add_job(
        threat_worker.scan_all_servers,
        trigger=IntervalTrigger(hours=12),
        id="threat_scan",
        replace_existing=True,
    )
    logger.info("Threat monitoring job registered (every 12 h)")

    # Proactive fleet-health digest — a friendly email of what needs attention across
    # the fleet. Runs daily at 08:00 UTC; the worker decides who's due (weekly users on
    # Mondays, daily users every day). Deterministic (no AI), reuses the email plumbing.
    from apscheduler.triggers.cron import CronTrigger
    from app.workers import digest_worker
    scheduler_service.get_scheduler().add_job(
        digest_worker.send_due_digests,
        trigger=CronTrigger(hour=8, minute=0, timezone="UTC"),
        id="fleet_digest",
        replace_existing=True,
    )
    logger.info("Fleet-health digest job registered (daily 08:00 UTC)")


@app.on_event("shutdown")
async def on_shutdown() -> None:
    """Run on application shutdown."""
    logger.info("ServerAlly backend shutting down...")
    scheduler_service.shutdown()
