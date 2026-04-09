import io
import zipfile

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import asyncpg

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.services.storage import generate_download_url, get_r2_client

class HighlightFeedbackBody(BaseModel):
    user_feedback: str | None = None


# Routes are mounted with /api/v1 prefix in main.py
router = APIRouter(tags=["highlights"])


@router.get("/videos/{video_id}/highlights")
async def list_highlights(
    video_id: str,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
):
    video = await db.fetchrow(
        "SELECT id FROM videos WHERE id = $1 AND user_id = $2", video_id, user_id
    )
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    rows = await db.fetch(
        """SELECT id, start_time_ms, end_time_ms, highlight_score, sub_highlight_type,
                  shot_type, shot_quality, point_scored, rally_length, r2_key_clip, user_feedback
           FROM highlights
           WHERE video_id = $1 AND sub_highlight_type != 'lowlight'
           ORDER BY highlight_score DESC""",
        video_id,
    )
    return [dict(r) for r in rows]


@router.get("/videos/{video_id}/lowlights")
async def list_lowlights(
    video_id: str,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
):
    video = await db.fetchrow(
        "SELECT id FROM videos WHERE id = $1 AND user_id = $2", video_id, user_id
    )
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    rows = await db.fetch(
        """SELECT id, start_time_ms, end_time_ms, highlight_score, lowlight_type,
                  shot_quality, r2_key_clip, user_feedback
           FROM highlights
           WHERE video_id = $1 AND sub_highlight_type = 'lowlight'
           ORDER BY shot_quality ASC""",
        video_id,
    )
    return [dict(r) for r in rows]


@router.get("/highlights/{highlight_id}/download")
async def get_clip_download_url(
    highlight_id: str,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
):
    row = await db.fetchrow(
        """SELECT h.id, h.r2_key_clip, v.user_id
           FROM highlights h
           JOIN videos v ON h.video_id = v.id
           WHERE h.id = $1""",
        highlight_id,
    )
    if not row or str(row["user_id"]) != user_id:
        raise HTTPException(status_code=404, detail="Highlight not found")
    if not row["r2_key_clip"]:
        raise HTTPException(status_code=409, detail="Clip not yet extracted")

    url = generate_download_url(row["r2_key_clip"], expires_in=3600)
    return {"download_url": url}


@router.get("/videos/{video_id}/clips/download-zip")
async def download_clips_zip(
    video_id: str,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
):
    """
    Stream a ZIP archive of all extracted clips for a video.
    Clips are organized into subfolders by shot_type (e.g. drive/, dink/, erne/).
    """
    video = await db.fetchrow(
        "SELECT id FROM videos WHERE id = $1 AND user_id = $2", video_id, user_id
    )
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    rows = await db.fetch(
        """SELECT id, shot_type, r2_key_clip
           FROM highlights
           WHERE video_id = $1 AND r2_key_clip IS NOT NULL
           ORDER BY highlight_score DESC""",
        video_id,
    )
    if not rows:
        raise HTTPException(status_code=409, detail="No clips available yet")

    client = get_r2_client()

    def generate_zip():
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for row in rows:
                shot_type = row["shot_type"] or "unknown"
                clip_id = str(row["id"])
                r2_key = row["r2_key_clip"]
                filename = f"{shot_type}/{clip_id}.mp4"
                try:
                    obj = client.get_object(Bucket=settings.r2_bucket_name, Key=r2_key)
                    zf.writestr(filename, obj["Body"].read())
                except Exception:
                    pass  # skip clips that fail to download
        buf.seek(0)
        yield from buf

    return StreamingResponse(
        generate_zip(),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=clips_{video_id[:8]}.zip"},
    )


@router.patch("/highlights/{highlight_id}")
async def update_highlight_feedback(
    highlight_id: str,
    body: HighlightFeedbackBody,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
):
    """Update user feedback (liked/disliked) on a highlight."""
    feedback = body.user_feedback
    if feedback not in ("liked", "disliked", None):
        raise HTTPException(status_code=422, detail="user_feedback must be 'liked', 'disliked', or null")

    result = await db.fetchrow(
        """UPDATE highlights h SET user_feedback = $1
           FROM videos v
           WHERE h.id = $2 AND h.video_id = v.id AND v.user_id = $3
           RETURNING h.id""",
        feedback, highlight_id, user_id,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Highlight not found")
    return {"status": "updated"}
