"""
Celery task for reel generation.
Triggered by the reels API (on-demand) and auto-triggered at the end of run_ai_pipeline (auto-generated types).
"""
from __future__ import annotations

import asyncio
import json

import asyncpg

from app.config import settings
from app.services.reel import assemble_and_upload, generate_share_token, generate_share_url
from app.workers.celery_app import celery

_AUTO_GENERATED_TYPES = [
    "highlight_montage",
    "my_best_plays",
    "game_recap",
    "points_of_improvement",
]


def _db_update_reel(reel_id: str, status: str, r2_key: str | None = None,
                    share_token: str | None = None) -> None:
    """Sync DB update from Celery worker thread."""
    async def _update():
        conn = await asyncpg.connect(settings.database_url)
        try:
            if r2_key:
                await conn.execute(
                    """UPDATE reels SET status = $1, r2_key = $2, share_token = $3 WHERE id = $4""",
                    status, r2_key, share_token, reel_id,
                )
            else:
                await conn.execute("UPDATE reels SET status = $1 WHERE id = $2", status, reel_id)
        finally:
            await conn.close()

    asyncio.run(_update())


def _fetch_clips_and_lowlights(video_id: str) -> tuple[list[dict], list[dict]]:
    """Fetch all highlights and lowlights for a video from DB."""
    async def _fetch():
        conn = await asyncpg.connect(settings.database_url)
        try:
            highlights = await conn.fetch(
                """SELECT id, highlight_score, shot_type, sub_highlight_type,
                          attributed_player_role, r2_key_clip, start_time_ms, shot_quality
                   FROM highlights
                   WHERE video_id = $1 AND sub_highlight_type != 'lowlight'
                   AND r2_key_clip IS NOT NULL""",
                video_id,
            )
            lowlights = await conn.fetch(
                """SELECT id, highlight_score, shot_quality, sub_highlight_type, r2_key_clip
                   FROM highlights
                   WHERE video_id = $1 AND sub_highlight_type = 'lowlight'
                   AND r2_key_clip IS NOT NULL""",
                video_id,
            )
            return [dict(h) for h in highlights], [dict(lo) for lo in lowlights]
        finally:
            await conn.close()

    return asyncio.run(_fetch())


def _get_user_center_x(video_id: str) -> float:
    """Get the user player's average horizontal position (for smart vertical crop)."""
    async def _fetch():
        conn = await asyncpg.connect(settings.database_url)
        try:
            row = await conn.fetchrow(
                """SELECT seed_frame_bbox FROM video_players
                   WHERE video_id = $1 AND role = 'user'""",
                video_id,
            )
            if row and row["seed_frame_bbox"]:
                bbox = (
                    json.loads(row["seed_frame_bbox"])
                    if isinstance(row["seed_frame_bbox"], str)
                    else row["seed_frame_bbox"]
                )
                x = bbox.get("x", 0)
                w_box = bbox.get("w", 100)
                frame_w = bbox.get("frame_w", 1920)
                return (x + w_box / 2) / frame_w
        finally:
            await conn.close()
        return 0.5  # default center

    return asyncio.run(_fetch())


@celery.task(bind=True, name="app.workers.reel_gen.generate_reel", max_retries=2)
def generate_reel(
    self,
    reel_id: str,
    video_id: str,
    user_id: str,
    output_type: str,
    format: str = "horizontal",
    music_dir: str = "backend/static/music",
) -> None:
    """
    Generate a reel for the given reel_id.
    Updates reel status → 'generating' → 'ready' (or 'failed').
    """
    _db_update_reel(reel_id, "generating")
    try:
        clips, lowlights = _fetch_clips_and_lowlights(video_id)
        user_center_x = _get_user_center_x(video_id)

        r2_key = assemble_and_upload(
            reel_id=reel_id,
            output_type=output_type,
            clips=clips,
            lowlights=lowlights,
            format=format,
            user_center_x=user_center_x,
            music_dir=music_dir,
        )

        share_token = generate_share_token()
        _db_update_reel(reel_id, "ready", r2_key=r2_key, share_token=share_token)

    except ValueError as exc:
        # Deterministic failures (e.g. no clips available) — don't retry
        _db_update_reel(reel_id, "failed")
        raise
    except Exception as exc:
        _db_update_reel(reel_id, "failed")
        raise self.retry(exc=exc, countdown=60)


async def trigger_auto_generated_reels(video_id: str, user_id: str) -> None:
    """
    Called from the API router (async context) to queue all auto-generated reel types.
    Creates DB rows for each reel type then dispatches Celery tasks.
    """
    conn = await asyncpg.connect(settings.database_url)
    try:
        reel_ids = {}
        for output_type in _AUTO_GENERATED_TYPES:
            existing = await conn.fetchrow(
                "SELECT id FROM reels WHERE video_id = $1 AND output_type = $2",
                video_id, output_type,
            )
            if existing:
                continue
            row = await conn.fetchrow(
                """INSERT INTO reels (user_id, video_id, output_type, format, auto_generated)
                   VALUES ($1, $2, $3, 'horizontal', TRUE)
                   RETURNING id""",
                user_id, video_id, output_type,
            )
            reel_ids[output_type] = str(row["id"])
    finally:
        await conn.close()

    for output_type, reel_id in reel_ids.items():
        generate_reel.delay(
            reel_id=reel_id,
            video_id=video_id,
            user_id=user_id,
            output_type=output_type,
        )


def trigger_auto_generated_reels_sync(video_id: str, user_id: str) -> None:
    """Sync wrapper — called from Celery worker (no running event loop)."""
    asyncio.run(trigger_auto_generated_reels(video_id, user_id))
