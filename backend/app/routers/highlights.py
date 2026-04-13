import io
import json
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


async def _update_user_preferences(
    db: asyncpg.Connection, user_id: str, shot_type: str, feedback: str
) -> None:
    """Adjust shot_type_weights in users.highlight_preferences based on clip feedback."""
    row = await db.fetchrow(
        "SELECT highlight_preferences FROM users WHERE id = $1", user_id
    )
    prefs = dict(row["highlight_preferences"] or {}) if row else {}
    weights = prefs.get("shot_type_weights", {})
    current = float(weights.get(shot_type, 1.0))
    delta = 0.05 if feedback == "liked" else -0.05
    weights[shot_type] = round(max(0.3, min(2.0, current + delta)), 4)
    prefs["shot_type_weights"] = weights
    prefs[f"{feedback}_count"] = prefs.get(f"{feedback}_count", 0) + 1
    await db.execute(
        "UPDATE users SET highlight_preferences = $1::jsonb WHERE id = $2",
        json.dumps(prefs), user_id,
    )


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
        """SELECT id, shot_type, sub_highlight_type, lowlight_type, r2_key_clip
           FROM highlights
           WHERE video_id = $1 AND r2_key_clip IS NOT NULL
           ORDER BY highlight_score DESC""",
        video_id,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No clips were detected in this video")

    client = get_r2_client()

    def generate_zip():
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
            for row in rows:
                is_lowlight = row["sub_highlight_type"] == "lowlight"
                if is_lowlight:
                    folder = "points_to_improve"
                    label = row["lowlight_type"] or "error"
                else:
                    folder = "highlights"
                    label = row["shot_type"] or "unknown"
                filename = f"{folder}/{label}/{str(row['id'])}.mp4"
                try:
                    obj = client.get_object(Bucket=settings.r2_bucket_name, Key=row["r2_key_clip"])
                    zf.writestr(filename, obj["Body"].read())
                except Exception:
                    pass  # skip clips that fail to download; do not abort the whole archive
        buf.seek(0)
        while chunk := buf.read(65536):
            yield chunk

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

    # Update user shot-type preferences based on feedback
    if feedback is not None:
        shot_row = await db.fetchrow(
            "SELECT shot_type FROM highlights WHERE id = $1", highlight_id
        )
        if shot_row and shot_row["shot_type"]:
            await _update_user_preferences(db, user_id, shot_row["shot_type"], feedback)

    return {"status": "updated"}
