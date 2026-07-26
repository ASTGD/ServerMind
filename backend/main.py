import logging
from contextlib import asynccontextmanager

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
from app.routers import autopilot as autopilot_router
from app.routers import branding as branding_router
from app.routers import status_pages as status_pages_router
from app.routers import logs as logs_router
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
from app.routers import escalation as escalation_router
from app.routers import api_v1 as api_v1_router
from app.routers import integrations as integrations_router
from app.routers import memories as memories_router
from app.routers import mcp_admin as mcp_admin_router
from app.routers import uptime as uptime_router
from app.routers import team as team_router
from app.routers import usage as usage_router
from app.services import backup_service, playbook_service, scheduler_service
from app.services.rate_limit_service import limiter
from app.websocket import terminal as ws_handlers
from app.websocket import rdp_tunnel as ws_rdp
from app.workers import metrics_worker
from app.mcp.server import mcp_server  # MCP server (docs/MCP-SERVER-PLAN.md)

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


async def _start_background_jobs() -> None:
    """Scheduler + metrics/threat/digest jobs — must run in exactly ONE process.

    When scaling web workers horizontally, set ENABLE_SCHEDULER=false on the extra
    workers (and run a single dedicated process with it enabled).
    """
    if not settings.ENABLE_SCHEDULER:
        logger.info("Scheduler disabled on this worker (ENABLE_SCHEDULER=false)")
        return

    # Start APScheduler, load saved tasks, and register metrics collection
    scheduler_service.start()
    await scheduler_service.load_all_tasks()
    await backup_service.load_all_backups()
    # Autopilot — Ally's scheduled missions (docs/PRO-FEATURES-PLAN.md §4 #1+#2).
    from app.services import autopilot_service
    await autopilot_service.load_all_tasks()
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

    # Uptime monitoring — probe each site FROM ServerAlly (not from the server, which
    # would pass while DNS/firewall/the whole box is unreachable). Sweeps every minute;
    # each monitor is only probed when its own interval has elapsed.
    from app.workers import uptime_worker
    scheduler_service.get_scheduler().add_job(
        uptime_worker.check_due_monitors,
        trigger=IntervalTrigger(minutes=1),
        id="uptime_checks",
        replace_existing=True,
        max_instances=1,  # a slow sweep must never overlap itself
    )
    scheduler_service.get_scheduler().add_job(
        uptime_worker.prune_old_checks,
        trigger=IntervalTrigger(hours=24),
        id="uptime_prune",
        replace_existing=True,
    )
    scheduler_service.get_scheduler().add_job(
        uptime_worker.check_certificates,
        trigger=IntervalTrigger(hours=12),
        id="cert_expiry",
        replace_existing=True,
        max_instances=1,
    )
    logger.info("Uptime monitoring job registered (sweep every 1 min, certs every 12 h)")

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

    # Monthly client reports — the branded "here is what we did for you" email an agency
    # sends its own client. Checked daily at 09:00 UTC; the worker sends only the
    # subscriptions whose send day is today and that have not already gone out this month.
    from app.workers import client_report_worker
    scheduler_service.get_scheduler().add_job(
        client_report_worker.send_due_reports,
        trigger=CronTrigger(hour=9, minute=0, timezone="UTC"),
        id="client_reports",
        replace_existing=True,
    )
    logger.info("Client report delivery job registered (daily 09:00 UTC)")

    # On-call escalation — climbs each open incident's ladder until somebody acknowledges.
    # Every minute, because the point of the feature is that a 5-minute step fires at 5
    # minutes. All the judgement is in the pure escalation_service; this only sends.
    from app.workers import escalation_worker
    scheduler_service.get_scheduler().add_job(
        escalation_worker.run_escalations,
        trigger=IntervalTrigger(minutes=1),
        id="escalation",
        replace_existing=True,
        max_instances=1,
    )
    logger.info("On-call escalation job registered (every 1 min)")

    # Webhook delivery — posts queued events to the customer's endpoints, with backoff.
    from app.workers import webhook_worker
    scheduler_service.get_scheduler().add_job(
        webhook_worker.run_deliveries,
        trigger=IntervalTrigger(minutes=1),
        id="webhook_deliveries",
        replace_existing=True,
        max_instances=1,
    )
    scheduler_service.get_scheduler().add_job(
        webhook_worker.prune_deliveries,
        trigger=IntervalTrigger(hours=24),
        id="webhook_prune",
        replace_existing=True,
    )
    logger.info("Webhook delivery job registered (every 1 min)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """App lifespan. Runs existing startup, holds the MCP session manager open for
    the app's lifetime, then runs existing shutdown.

    NOTE: a custom lifespan REPLACES @app.on_event, so all prior startup/shutdown
    logic lives here now. The MCP Streamable-HTTP transport needs its session
    manager running inside the app lifespan (docs/MCP-SERVER-PLAN.md §4).
    """
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

    await _start_background_jobs()

    # The MCP Streamable-HTTP session manager must run for the app's lifetime.
    async with mcp_server.session_manager.run():
        logger.info("MCP server ready at /mcp (serverally_mcp)")
        yield

    logger.info("ServerAlly backend shutting down...")
    scheduler_service.shutdown()


app = FastAPI(
    title=settings.APP_NAME,
    description="AI-powered server management platform",
    version=settings.APP_VERSION,
    docs_url=None if _is_prod else "/docs",
    redoc_url=None if _is_prod else "/redoc",
    lifespan=lifespan,
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
app.include_router(branding_router.router)  # /api/branding + client reports
app.include_router(status_pages_router.router)  # /api/status-pages + public /api/public/status/{slug}
app.include_router(autopilot_router.router)  # /api/autopilot — scheduled missions
app.include_router(logs_router.router)  # /api/servers/{id}/logs — server log viewer
app.include_router(uptime_router.router)
app.include_router(escalation_router.router)  # /api/escalation — on-call paging
app.include_router(integrations_router.router)  # /api/api-keys, /api/webhooks — browser-only
app.include_router(api_v1_router.router)  # /api/v1 — API-key only, bounded on purpose
app.include_router(mcp_admin_router.router)  # /api/mcp — Connected applications (Phase 4)
app.include_router(entitlements_router.router)
app.include_router(ws_handlers.router)
app.include_router(ws_rdp.router)  # /ws/rdp — live Remote Desktop via guacd

# MCP server (docs/MCP-SERVER-PLAN.md) — a customer's own AI client (Claude Code,
# Desktop, ChatGPT, Cursor) → our bounded, credential-free tools. Streamable HTTP at
# exactly /mcp; its session manager is started in the lifespan above.
_mcp_app = mcp_server.streamable_http_app()
if settings.MCP_REQUIRE_AUTH:
    # Phase 1: /mcp is an OAuth 2.1 Resource Server. The Authorization Server lives at the
    # root origin (issuer = MCP_BASE_URL) so .well-known discovery is unambiguous, and the
    # browser consent page is /oauth/consent.
    from app.mcp.http_auth import guard_mcp_app, oauth_root_routes
    from app.mcp.rate_limit import OAuthRateLimitMiddleware
    from app.routers import mcp_oauth as mcp_oauth_router

    app.mount("/mcp", guard_mcp_app(_mcp_app))
    app.include_router(mcp_oauth_router.router)     # /oauth/consent (login + approve)
    app.router.routes.extend(oauth_root_routes())   # /authorize /token /register /revoke + .well-known
    # Per-IP throttle on the OAuth mutation endpoints (brute-force + DCR-spam).
    app.add_middleware(OAuthRateLimitMiddleware)
    logger.info("MCP OAuth enabled — issuer=%s, resource=%s/mcp", settings.MCP_BASE_URL, settings.MCP_BASE_URL)
else:
    # LOCAL DEV ONLY — authless (Phase-0 behaviour); the dev-user resolver picks the caller.
    app.mount("/mcp", _mcp_app)
    logger.warning("MCP auth DISABLED (MCP_REQUIRE_AUTH=false) — local dev only, do not ship")


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "app": settings.APP_NAME}
