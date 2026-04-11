import asyncio
import logging
import asyncpg
from app.workers.celery_app import celery
from app.config import settings
from app.services.storage import delete_object
from app.services.usage_guard import fetch_snapshot, evaluate, send_alerts

logger = logging.getLogger(__name__)


async def find_stale_jobs() -> list[dict]:
    """Find videos stuck in 'identifying' for more than 24 hours."""
    conn = await asyncpg.connect(settings.database_url)
    try:
        rows = await conn.fetch(
            """SELECT id, r2_key_original, r2_key_processed
               FROM videos
               WHERE status = 'identifying'
               AND identify_started_at < NOW() - INTERVAL '24 hours'"""
        )
        return [dict(r) for r in rows]
    finally:
        await conn.close()


async def cancel_stale_job(video_id: str, r2_key_processed: str | None) -> None:
    """Mark a job as timed_out, set 7-day cleanup window, and delete R2 working copy."""
    conn = await asyncpg.connect(settings.database_url)
    try:
        await conn.execute(
            """UPDATE videos
               SET status = 'timed_out',
                   cleanup_after = NOW() + INTERVAL '7 days'
               WHERE id = $1""",
            video_id,
        )
    finally:
        await conn.close()

    # Delete processed working copy (saves R2 storage) — keep original for re-trigger
    if r2_key_processed:
        try:
            delete_object(r2_key_processed)
        except Exception as exc:
            logger.warning("R2 delete failed for %s: %s", r2_key_processed, exc)


@celery.task(name="app.workers.cleanup.cleanup_stale_jobs")
def cleanup_stale_jobs() -> dict:
    """
    Celery beat task: runs every hour.
    Cancels jobs stuck in 'identifying' for > 24 hours.
    Returns dict with count of cancelled jobs.
    """
    stale = asyncio.run(find_stale_jobs())
    logger.info("Cleanup found %d stale job(s)", len(stale))
    cancelled = 0

    for video in stale:
        try:
            asyncio.run(cancel_stale_job(
                video["id"],
                video.get("r2_key_processed"),
            ))
            cancelled += 1
        except Exception as exc:
            logger.warning("Failed to cancel stale job %s: %s", video["id"], exc)

    logger.info("Cleanup cancelled %d job(s)", cancelled)
    return {"cancelled": cancelled}


# Retention policies: (table, column, days)
_RETENTION_POLICIES = [
    ("videos", "r2_key_original", 7),
    ("videos", "r2_key_processed", 14),
    ("highlights", "r2_key", 30),
    ("reels", "r2_key", 60),
]


async def _enforce_r2_lifecycle_async() -> dict:
    """Delete R2 objects past their retention window and null the DB column."""
    total_deleted = 0

    for table, col, days in _RETENTION_POLICIES:
        conn = await asyncpg.connect(settings.database_url)
        try:
            rows = await conn.fetch(
                f"""SELECT id, {col} FROM {table}
                    WHERE {col} IS NOT NULL
                    AND created_at < NOW() - INTERVAL '{days} days'
                    LIMIT 100"""
            )
            for row in rows:
                try:
                    delete_object(row[col])
                    await conn.execute(
                        f"UPDATE {table} SET {col} = NULL WHERE id = $1",
                        row["id"],
                    )
                    total_deleted += 1
                except Exception as exc:
                    logger.warning(
                        "R2 lifecycle: failed to delete %s from %s.%s: %s",
                        row[col], table, col, exc,
                    )
        finally:
            await conn.close()

    return {"deleted": total_deleted}


@celery.task(name="app.workers.cleanup.enforce_r2_lifecycle")
def enforce_r2_lifecycle() -> dict:
    """
    Runs every hour. Deletes R2 objects past their retention window and nulls
    the corresponding DB column so re-download attempts get a clear 404.
    Returns dict with count of objects deleted.
    """
    return asyncio.run(_enforce_r2_lifecycle_async())


async def _check_usage_async() -> dict:
    """Fetch usage snapshot, evaluate thresholds, and send alerts."""
    conn = await asyncpg.connect(settings.database_url)
    try:
        snap = await fetch_snapshot(conn)
        snap = await evaluate(snap)
        await send_alerts(snap)
        return {"alerts": len(snap.alerts), "blocks": len(snap.blocks)}
    finally:
        await conn.close()


@celery.task(name="app.workers.cleanup.check_usage_and_cleanup")
def check_usage_and_cleanup() -> dict:
    """Runs daily at 8am UTC. Fetches usage snapshot and sends alerts if thresholds exceeded."""
    return asyncio.run(_check_usage_async())
