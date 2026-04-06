import asyncio
import asyncpg
from app.workers.celery_app import celery
from app.config import settings
from app.services.storage import delete_object


async def find_stale_jobs() -> list[dict]:
    """Find videos stuck in 'identifying' for more than 24 hours."""
    conn = await asyncpg.connect(settings.database_url)
    try:
        rows = await conn.fetch(
            """SELECT id, r2_key_original, r2_key_processed, user_id
               FROM videos
               WHERE status = 'identifying'
               AND identify_started_at < NOW() - INTERVAL '24 hours'"""
        )
        return [dict(r) for r in rows]
    finally:
        await conn.close()


async def cancel_stale_job(video_id: str, r2_key_original: str, r2_key_processed: str | None) -> None:
    """Mark a job as timed_out and clean up R2 working copy."""
    conn = await asyncpg.connect(settings.database_url)
    try:
        await conn.execute(
            "UPDATE videos SET status = 'timed_out' WHERE id = $1", video_id
        )
    finally:
        await conn.close()

    # Delete processed working copy (saves R2 storage) — keep original for re-trigger
    if r2_key_processed:
        try:
            delete_object(r2_key_processed)
        except Exception:
            pass  # Don't fail cleanup if R2 delete errors


async def schedule_original_deletion(video_id: str) -> None:
    """Set cleanup_after to 7 days from now — R2 lifecycle policy handles actual deletion."""
    conn = await asyncpg.connect(settings.database_url)
    try:
        await conn.execute(
            "UPDATE videos SET cleanup_after = NOW() + INTERVAL '7 days' WHERE id = $1",
            video_id,
        )
    finally:
        await conn.close()


@celery.task(name="app.workers.cleanup.cleanup_stale_jobs")
def cleanup_stale_jobs() -> dict:
    """
    Celery beat task: runs every hour.
    Cancels jobs stuck in 'identifying' for > 24 hours.
    Returns dict with count of cancelled jobs.
    """
    stale = asyncio.run(find_stale_jobs())
    cancelled = 0

    for video in stale:
        asyncio.run(cancel_stale_job(
            video["id"],
            video["r2_key_original"],
            video.get("r2_key_processed"),
        ))
        asyncio.run(schedule_original_deletion(video["id"]))
        cancelled += 1

    return {"cancelled": cancelled}
