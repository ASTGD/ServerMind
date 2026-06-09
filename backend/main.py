import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import AsyncSessionLocal
from app.routers import auth as auth_router
from app.routers import commands as commands_router
from app.routers import files as files_router
from app.routers import monitoring as monitoring_router
from app.routers import playbooks as playbooks_router
from app.routers import scheduler as scheduler_router
from app.routers import scripts as scripts_router
from app.routers import servers as servers_router
from app.services import playbook_service, scheduler_service
from app.websocket import terminal as ws_handlers
from app.workers import metrics_worker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.APP_NAME,
    description="AI-powered server management platform",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth_router.router)
app.include_router(servers_router.router)
app.include_router(commands_router.router)
app.include_router(playbooks_router.router)
app.include_router(scripts_router.router)
app.include_router(scheduler_router.router)
app.include_router(monitoring_router.router)
app.include_router(files_router.router)
app.include_router(ws_handlers.router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "app": settings.APP_NAME}


@app.on_event("startup")
async def on_startup() -> None:
    """Run on application startup."""
    logger.info("ServerMind backend starting up...")
    async with AsyncSessionLocal() as db:
        await playbook_service.seed_if_empty(db)
    # Start APScheduler, load saved tasks, and register metrics collection
    scheduler_service.start()
    await scheduler_service.load_all_tasks()
    # Collect metrics every 5 minutes
    from apscheduler.triggers.interval import IntervalTrigger
    scheduler_service.get_scheduler().add_job(
        metrics_worker.collect_all_metrics,
        trigger=IntervalTrigger(minutes=5),
        id="metrics_collection",
        replace_existing=True,
    )
    logger.info("Metrics collection job registered (every 5 min)")


@app.on_event("shutdown")
async def on_shutdown() -> None:
    """Run on application shutdown."""
    logger.info("ServerMind backend shutting down...")
    scheduler_service.shutdown()
