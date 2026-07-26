"""The retention sweeps — the only scheduled job in the product that deletes customer data.

Each series is swept twice, and the ORDER and the FILTERS are the safety mechanism:

1. **Global sweep** at the most generous window. Applies to every row, so a row whose server
   or owner was deleted still gets cleaned up and nothing grows forever.
2. **Free sweep** at the shorter window, filtered on ``plan = 'free'`` *by name*.

Because the only query carrying a short cutoff selects Free accounts explicitly, a Pro
account — or one whose plan is NULL, misspelled, or a tier that does not exist yet — is never
matched by it and keeps the long window. Every way this can go wrong keeps more data.

``dry_run`` counts instead of deleting, so the first production run can be read before it is
trusted.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.alert import ServerMetric
from app.models.integration import WebhookDelivery, WebhookEndpoint
from app.models.server import Server
from app.models.uptime import UptimeCheck, UptimeMonitor
from app.models.user import User
from app.services import retention_service as retention

logger = logging.getLogger(__name__)


def _free_user_ids():
    """A subquery of Free accounts, selected by name.

    Deliberately ``== FREE`` rather than ``!= PRO``: the difference is what makes an unknown
    plan keep its data instead of losing it.
    """
    return select(User.id).where(User.plan == retention.FREE)


# ── Per-series row selectors ─────────────────────────────────────────────────
# Each returns (all_rows_before_cutoff, free_owned_rows_before_cutoff) as WHERE clauses.

def _metric_filters(cut_all: datetime, cut_free: datetime | None):
    all_rows = ServerMetric.recorded_at < cut_all
    free_rows = None
    if cut_free is not None:
        free_rows = (
            (ServerMetric.recorded_at < cut_free)
            & ServerMetric.server_id.in_(
                select(Server.id).where(Server.user_id.in_(_free_user_ids()))
            )
        )
    return all_rows, free_rows


def _uptime_filters(cut_all: datetime, cut_free: datetime | None):
    all_rows = UptimeCheck.checked_at < cut_all
    free_rows = None
    if cut_free is not None:
        free_rows = (
            (UptimeCheck.checked_at < cut_free)
            & UptimeCheck.monitor_id.in_(
                select(UptimeMonitor.id).where(UptimeMonitor.user_id.in_(_free_user_ids()))
            )
        )
    return all_rows, free_rows


def _webhook_filters(cut_all: datetime, cut_free: datetime | None):
    all_rows = WebhookDelivery.created_at < cut_all
    free_rows = None
    if cut_free is not None:
        free_rows = (
            (WebhookDelivery.created_at < cut_free)
            & WebhookDelivery.endpoint_id.in_(
                select(WebhookEndpoint.id).where(WebhookEndpoint.user_id.in_(_free_user_ids()))
            )
        )
    return all_rows, free_rows


_SERIES = {
    "metrics": (ServerMetric, _metric_filters),
    "uptime": (UptimeCheck, _uptime_filters),
    "webhooks": (WebhookDelivery, _webhook_filters),
}


async def _apply(db: AsyncSession, model, clause, kind: str, scope: str,
                 cut: datetime, dry_run: bool) -> int:
    """Delete (or count) the rows a clause selects."""
    if clause is None:
        return 0
    if dry_run:
        return int((await db.execute(
            select(func.count()).select_from(model).where(clause)
        )).scalar() or 0)
    result = await db.execute(delete(model).where(clause))
    deleted = int(result.rowcount or 0)
    retention.log_prune(kind, scope, deleted, cut)
    return deleted


async def sweep(kind: str, *, now: datetime | None = None, dry_run: bool = False) -> dict:
    """Sweep one series. Returns what was (or would be) removed."""
    if kind not in _SERIES:
        raise ValueError(f"Unknown retention kind '{kind}'")
    model, filters = _SERIES[kind]
    now = now or datetime.now(tz=timezone.utc)

    cut_all = retention.global_cutoff(kind, now)
    cut_free = retention.free_cutoff(kind, now)
    all_rows, free_rows = filters(cut_all, cut_free)

    async with AsyncSessionLocal() as db:
        # Global first: it is the least aggressive cutoff, so anything it removes would be
        # removed by the Free sweep anyway. Running it first keeps the Free sweep's work — and
        # therefore its blast radius — as small as possible.
        removed_all = await _apply(db, model, all_rows, kind, "all accounts", cut_all, dry_run)
        removed_free = await _apply(db, model, free_rows, kind, "free accounts",
                                    cut_free or cut_all, dry_run)
        if not dry_run:
            await db.commit()

    return {
        "kind": kind,
        "cutoff_all": cut_all.isoformat(),
        "cutoff_free": cut_free.isoformat() if cut_free else None,
        "removed_all": removed_all,
        "removed_free": removed_free,
        "dry_run": dry_run,
    }


async def run_retention(now: datetime | None = None, dry_run: bool = False) -> list[dict]:
    """Sweep every series. One failing series never stops the others."""
    out: list[dict] = []
    for kind in retention.KINDS:
        try:
            out.append(await sweep(kind, now=now, dry_run=dry_run))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Retention sweep failed for %s: %s", kind, exc)
            out.append({"kind": kind, "error": str(exc)})
    total = sum(r.get("removed_all", 0) + r.get("removed_free", 0) for r in out)
    logger.info("Retention run complete%s: %d row(s) across %d series",
                " (dry run)" if dry_run else "", total, len(out))
    return out
