from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import asyncpg

from app.auth import get_current_user
from app.database import get_db
from app.services.reel import generate_share_token, generate_share_url
from app.services.storage import generate_download_url

router = APIRouter(tags=["reels"])

_VALID_OUTPUT_TYPES = {
    "highlight_montage", "my_best_plays", "game_recap",
    "points_of_improvement", "best_shots", "scored_point_rally",
    "full_rally_replay", "single_shot_clip",
}
_VALID_FORMATS = {"vertical", "horizontal", "square"}


class CreateReelBody(BaseModel):
    video_id: str
    output_type: str
    format: str = "horizontal"


@router.get("/videos/{video_id}/reels")
async def list_reels(
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
        """SELECT id, output_type, format, status, duration_seconds, auto_generated, created_at
           FROM reels WHERE video_id = $1 ORDER BY created_at DESC""",
        video_id,
    )
    return [dict(r) for r in rows]


@router.post("/reels", status_code=201)
async def create_reel(
    body: CreateReelBody,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
):
    if body.output_type not in _VALID_OUTPUT_TYPES:
        raise HTTPException(status_code=422, detail=f"Invalid output_type: {body.output_type!r}")
    if body.format not in _VALID_FORMATS:
        raise HTTPException(status_code=422, detail=f"Invalid format: {body.format!r}")

    video = await db.fetchrow(
        "SELECT id FROM videos WHERE id = $1 AND user_id = $2 AND status = 'analyzed'",
        body.video_id, user_id,
    )
    if not video:
        raise HTTPException(status_code=404, detail="Analyzed video not found")

    row = await db.fetchrow(
        """INSERT INTO reels (user_id, video_id, output_type, format, auto_generated)
           VALUES ($1, $2, $3, $4, FALSE)
           RETURNING id, status""",
        user_id, body.video_id, body.output_type, body.format,
    )
    reel_id = str(row["id"])

    from app.workers.reel_gen import generate_reel
    generate_reel.delay(
        reel_id=reel_id,
        video_id=body.video_id,
        user_id=user_id,
        output_type=body.output_type,
        format=body.format,
    )

    return {"id": reel_id, "status": "queued", "output_type": body.output_type}


# NOTE: this route must be defined before /{reel_id} to prevent FastAPI matching "share" as reel_id
@router.get("/reels/share/{share_token}")
async def get_shared_reel(
    share_token: str,
    db: asyncpg.Connection = Depends(get_db),
):
    """Public endpoint — no auth required. Returns OG preview metadata + download URL."""
    row = await db.fetchrow(
        """SELECT r.id, r.output_type, r.format, r.duration_seconds, r.r2_key
           FROM reels r
           WHERE r.share_token = $1 AND r.status = 'ready'""",
        share_token,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Shared reel not found")

    download_url = generate_download_url(row["r2_key"], expires_in=86400) if row["r2_key"] else None
    return {
        "output_type": row["output_type"],
        "format": row["format"],
        "duration_seconds": row["duration_seconds"],
        "download_url": download_url,
    }


@router.get("/reels/{reel_id}")
async def get_reel(
    reel_id: str,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
):
    row = await db.fetchrow(
        """SELECT r.id, r.output_type, r.format, r.status, r.r2_key,
                  r.duration_seconds, r.auto_generated, r.share_token, r.created_at
           FROM reels r
           WHERE r.id = $1 AND r.user_id = $2""",
        reel_id, user_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Reel not found")

    result = dict(row)
    if row["status"] == "ready" and row["r2_key"]:
        result["download_url"] = generate_download_url(row["r2_key"], expires_in=3600)
    if row["share_token"]:
        result["share_url"] = generate_share_url(row["share_token"])

    return result


@router.post("/reels/{reel_id}/share")
async def share_reel(
    reel_id: str,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
):
    row = await db.fetchrow(
        "SELECT id, status, share_token, r2_key FROM reels WHERE id = $1 AND user_id = $2",
        reel_id, user_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Reel not found")
    if row["status"] != "ready":
        raise HTTPException(status_code=409, detail="Reel is not ready yet")

    token = row["share_token"] or generate_share_token()
    if not row["share_token"]:
        await db.execute("UPDATE reels SET share_token = $1 WHERE id = $2", token, reel_id)

    return {"share_url": generate_share_url(token), "share_token": token}
