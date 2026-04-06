import asyncio
import logging
import asyncpg
from app.workers.celery_app import celery
from app.config import settings
from app.services.storage import delete_object

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
