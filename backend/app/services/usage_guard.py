"""
usage_guard.py — Free tier usage monitoring and enforcement.

Fetches current usage from Supabase (DB size), Cloudflare R2 (storage),
and Upstash (command counts / memory), then evaluates thresholds and
raises QuotaExceededError when critical limits would block new ingest jobs.

Designed to be called from both FastAPI route handlers and Celery workers —
accepts a raw asyncpg connection rather than using FastAPI's get_db dependency.
"""

import asyncio
import logging
from dataclasses import dataclass, field

import boto3
import httpx

from app.config import (
    ALERT_THRESHOLD_PCT,
    BLOCK_THRESHOLD_PCT,
    FREE_TIER_LIMITS,
    settings,
)

logger = logging.getLogger("usage_guard")


# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass
class UsageSnapshot:
    supabase_db_bytes: int = 0
    r2_storage_bytes: int = 0
    upstash_commands_today: int = 0
    upstash_memory_bytes: int = 0
    total_users: int = 0
    alerts: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)


class QuotaExceededError(RuntimeError):
    """Raised when a critical free tier limit is at or above BLOCK_THRESHOLD_PCT."""


# ── Internal fetch helpers ────────────────────────────────────────────────────


def _fetch_r2_storage_bytes() -> int:
    """Synchronous boto3 call — intended to be run in a thread executor."""
    client = boto3.client(
        "s3",
        endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name="auto",
    )
    total_bytes = 0
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=settings.r2_bucket_name):
        for obj in page.get("Contents", []):
            total_bytes += obj.get("Size", 0)
    return total_bytes


async def _fetch_upstash_usage() -> tuple[int, int]:
    """
    Returns (commands_today, memory_bytes).

    If upstash_rest_url is empty or the call fails, returns (0, 0) — monitoring
    failures must never block normal operation.
    """
    if not settings.upstash_rest_url:
        return 0, 0

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{settings.upstash_rest_url}/info",
                headers={"Authorization": f"Bearer {settings.upstash_rest_token}"},
            )
            resp.raise_for_status()
            data = resp.json()
            # Upstash /info returns a flat dict or a nested result dict
            if isinstance(data, dict) and "result" in data:
                info = data["result"]
            else:
                info = data
            commands = int(info.get("total_commands_processed", 0))
            memory = int(info.get("used_memory", 0))
            return commands, memory
    except Exception as exc:  # noqa: BLE001
        logger.warning("Upstash /info fetch failed (returning 0): %s", exc)
        return 0, 0


# ── Public API ────────────────────────────────────────────────────────────────


async def fetch_snapshot(db) -> UsageSnapshot:
    """
    Fetch current usage from all services and return a UsageSnapshot.

    Parameters
    ----------
    db:
        An asyncpg connection (or pool connection).
    """
    snap = UsageSnapshot()

    # 1. Supabase DB size
    row = await db.fetchrow(
        "SELECT pg_database_size(current_database()) AS size"
    )
    snap.supabase_db_bytes = row["size"] if row else 0

    # 2. R2 storage (boto3 is synchronous — run in thread executor)
    snap.r2_storage_bytes = await asyncio.to_thread(_fetch_r2_storage_bytes)

    # 3. Upstash command count + memory
    snap.upstash_commands_today, snap.upstash_memory_bytes = (
        await _fetch_upstash_usage()
    )

    # 4. Total registered users
    row = await db.fetchrow("SELECT COUNT(*) AS cnt FROM users")
    snap.total_users = row["cnt"] if row else 0

    return snap


def evaluate(snap: UsageSnapshot) -> UsageSnapshot:
    """
    Populate snap.alerts and snap.blocks by comparing each metric against
    ALERT_THRESHOLD_PCT and BLOCK_THRESHOLD_PCT.

    Returns the same snapshot object (mutated in-place) for convenience.
    """
    # (field_name, limit_key, is_critical)
    checks: list[tuple[str, str, bool]] = [
        ("supabase_db_bytes",     "supabase_db_bytes",        True),
        ("r2_storage_bytes",      "r2_storage_bytes",         True),
        ("upstash_commands_today","upstash_commands_per_day", True),
        ("upstash_memory_bytes",  "upstash_memory_bytes",     False),
    ]

    for field_name, limit_key, is_critical in checks:
        current: int = getattr(snap, field_name)
        limit: int = FREE_TIER_LIMITS[limit_key]
        pct: float = current / limit if limit > 0 else 0.0

        msg = (
            f"{field_name} at {pct:.0%} of free tier "
            f"({current:,} / {limit:,} bytes)"
        )

        if pct >= BLOCK_THRESHOLD_PCT and is_critical:
            snap.blocks.append(msg)
        elif pct >= ALERT_THRESHOLD_PCT:
            snap.alerts.append(msg)

    return snap


async def assert_can_ingest(db) -> None:
    """
    Raise QuotaExceededError if any critical free tier limit is at or above
    BLOCK_THRESHOLD_PCT.  Call this at the start of every ingest job.
    """
    snap = await fetch_snapshot(db)
    evaluate(snap)
    if snap.blocks:
        raise QuotaExceededError(
            "Free tier critical limits exceeded — new ingest jobs are blocked:\n"
            + "\n".join(f"  • {msg}" for msg in snap.blocks)
        )


async def send_alerts(snap: UsageSnapshot) -> None:
    """
    Emit an ERROR-level log entry when any alert or block is present so that
    Sentry (or any other log-based alerting integration) can capture it.
    """
    if not snap.alerts and not snap.blocks:
        return

    lines = []
    if snap.blocks:
        lines.append("BLOCKS (ingest disabled):")
        lines.extend(f"  • {m}" for m in snap.blocks)
    if snap.alerts:
        lines.append("ALERTS (approaching limit):")
        lines.extend(f"  • {m}" for m in snap.alerts)

    logger.error("FREE_TIER_ALERT\n%s", "\n".join(lines))
