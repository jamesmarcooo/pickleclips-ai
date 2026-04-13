import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
import asyncpg

from app.auth import get_current_user
from app.config import ALLOWED_USER_CAP
from app.database import get_db
from app.services import storage

# Routes are mounted with /api/v1 prefix in main.py
router = APIRouter(tags=["videos"])


class CreateMultipartRequest(BaseModel):
    filename: str
    content_type: str = "video/mp4"


class CompleteMultipartRequest(BaseModel):
    key: str
    upload_id: str
    parts: list[dict]  # [{"ETag": "...", "PartNumber": 1}, ...]


class TapIdentifyRequest(BaseModel):
    bbox_index: int  # 0-3, which bounding box the user tapped


class ConfirmIdentityRequest(BaseModel):
    confirmed: bool  # True = accept auto-selected bbox; False = fall back to 4-box tap


# ── Multipart upload coordination ─────────────────────────────────────────────

@router.post("/videos/multipart/create")
async def create_multipart_upload(
    body: CreateMultipartRequest,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
):
    # Enforce friends-only user cap for new (unseen) users
    exists = await db.fetchval("SELECT 1 FROM users WHERE id = $1", user_id)
    if not exists:
        user_count = await db.fetchval("SELECT COUNT(*) FROM users")
        if user_count >= ALLOWED_USER_CAP:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This instance is limited to invited users only.",
            )

    video_id = str(uuid.uuid4())
    key = f"videos/{video_id}/original.mp4"

    # Get upload_id from storage first — if this fails, no DB record is created
    upload_id = storage.generate_multipart_upload_id(key, body.content_type)

    await db.execute(
        """INSERT INTO videos (id, user_id, r2_key_original, original_filename, status)
           VALUES ($1, $2, $3, $4, 'uploading')""",
        video_id, user_id, key, body.filename,
    )

    return {"video_id": video_id, "upload_id": upload_id, "key": key}


@router.get("/videos/multipart/sign-part")
async def sign_multipart_part(
    key: str = Query(...),
    upload_id: str = Query(...),
    part_number: int = Query(..., ge=1, le=10000),
    user_id: str = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
):
    # Ownership check: key format is videos/{video_id}/original.mp4
    parts = key.split("/")
    if len(parts) < 2:
        raise HTTPException(status_code=422, detail="Invalid key format")
    video_id = parts[1]
    row = await db.fetchrow(
        "SELECT id FROM videos WHERE id = $1 AND user_id = $2", video_id, user_id
    )
    if not row:
        raise HTTPException(status_code=404, detail="Video not found")

    url = storage.sign_multipart_part(key, upload_id, part_number)
    return {"url": url}


@router.post("/videos/multipart/complete")
async def complete_multipart_upload(
    body: CompleteMultipartRequest,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
):
    parts = body.key.split("/")
    if len(parts) < 2:
        raise HTTPException(status_code=422, detail="Invalid key format")
    video_id = parts[1]
    row = await db.fetchrow(
        "SELECT id FROM videos WHERE id = $1 AND user_id = $2", video_id, user_id
    )
    if not row:
        raise HTTPException(status_code=404, detail="Video not found")

    # Normalize parts: Uppy sends lowercase keys, boto3 requires ETag + PartNumber
    normalized_parts = [
        {"ETag": p.get("ETag") or p.get("etag", ""), "PartNumber": p.get("PartNumber") or p.get("partNumber") or p.get("part_number")}
        for p in body.parts
    ]
    storage.complete_multipart_upload(body.key, body.upload_id, normalized_parts)
    return {"status": "ok"}


@router.delete("/videos/multipart/abort")
async def abort_multipart_upload(
    key: str = Query(...),
    upload_id: str = Query(...),
    user_id: str = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
):
    parts = key.split("/")
    if len(parts) < 2:
        raise HTTPException(status_code=422, detail="Invalid key format")
    video_id = parts[1]
    row = await db.fetchrow(
        "SELECT id FROM videos WHERE id = $1 AND user_id = $2", video_id, user_id
    )
    if not row:
        raise HTTPException(status_code=404, detail="Video not found")

    storage.abort_multipart_upload(key, upload_id)
    return {"status": "ok"}


# ── Video management ──────────────────────────────────────────────────────────

@router.post("/videos/{video_id}/retry")
async def retry_pipeline(
    video_id: str,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
):
    """Re-trigger the AI pipeline for a video stuck in 'processing' or 'failed' state."""
    import json as _json
    from app.workers.ingest import run_ai_pipeline, ingest_video

    video = await db.fetchrow(
        "SELECT id, user_id, status, metadata FROM videos WHERE id = $1", video_id
    )
    if not video or str(video["user_id"]) != user_id:
        raise HTTPException(status_code=404, detail="Video not found")
    if video["status"] not in ("processing", "failed", "identifying"):
        raise HTTPException(status_code=409, detail=f"Cannot retry video in '{video['status']}' state")

    raw_meta = video["metadata"]
    meta = _json.loads(raw_meta) if isinstance(raw_meta, str) else (raw_meta or {})
    seed_bbox = meta.get("selected_seed_bbox")

    if seed_bbox:
        await db.execute("UPDATE videos SET status = 'processing' WHERE id = $1", video_id)
        run_ai_pipeline.delay(video_id, user_id, seed_bbox)
        return {"status": "processing", "video_id": video_id}
    else:
        # No seed bbox stored — need user to re-identify
        await db.execute("UPDATE videos SET status = 'identifying' WHERE id = $1", video_id)
        return {"status": "identifying", "video_id": video_id, "message": "Please re-identify yourself in the video"}

@router.post("/videos/{video_id}/confirm")
async def confirm_upload(
    video_id: str,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
):
    """Called by frontend after multipart upload completes. Triggers the pipeline."""
    from app.workers.ingest import ingest_video  # lazy import — workers created in Task 7

    video = await db.fetchrow(
        "SELECT id, user_id FROM videos WHERE id = $1", video_id
    )
    if not video or str(video["user_id"]) != user_id:
        raise HTTPException(status_code=404, detail="Video not found")

    await db.execute(
        "UPDATE videos SET status = 'processing' WHERE id = $1", video_id
    )

    ingest_video.delay(video_id, user_id)

    return {"status": "processing", "video_id": video_id}


@router.get("/videos")
async def list_videos(
    user_id: str = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
):
    rows = await db.fetch(
        "SELECT id, status, uploaded_at, duration_seconds, resolution, original_filename FROM videos "
        "WHERE user_id = $1 ORDER BY uploaded_at DESC",
        user_id,
    )
    return [dict(r) for r in rows]


@router.get("/videos/{video_id}")
async def get_video(
    video_id: str,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
):
    row = await db.fetchrow(
        "SELECT * FROM videos WHERE id = $1 AND user_id = $2", video_id, user_id
    )
    if not row:
        raise HTTPException(status_code=404, detail="Video not found")
    return dict(row)


@router.post("/videos/{video_id}/generate-reels", status_code=202)
async def generate_reels(
    video_id: str,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
):
    """
    Trigger auto-generation of the standard reel set for an analyzed video.
    Returns immediately — reel generation runs asynchronously.
    Idempotent: skips reel types that already exist for this video.
    """
    from app.workers.reel_gen import trigger_auto_generated_reels

    video = await db.fetchrow(
        "SELECT id, status FROM videos WHERE id = $1 AND user_id = $2", video_id, user_id
    )
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    if video["status"] != "analyzed":
        raise HTTPException(status_code=409, detail=f"Video is not analyzed yet (status: {video['status']})")

    await trigger_auto_generated_reels(video_id=video_id, user_id=user_id)
    return {"status": "queued", "video_id": video_id}


@router.delete("/videos/{video_id}")
async def delete_video(
    video_id: str,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
):
    row = await db.fetchrow(
        "SELECT r2_key_original, r2_key_processed FROM videos WHERE id = $1 AND user_id = $2",
        video_id, user_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Video not found")

    if row["r2_key_original"]:
        storage.delete_object(row["r2_key_original"])
    if row["r2_key_processed"]:
        storage.delete_object(row["r2_key_processed"])

    await db.execute("DELETE FROM videos WHERE id = $1", video_id)
    return {"status": "deleted"}


# ── Player identification ──────────────────────────────────────────────────────

@router.get("/videos/{video_id}/identify")
async def get_identify_frame(
    video_id: str,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
):
    """Return the seed frame URL + bounding boxes for tap-to-identify."""
    video = await db.fetchrow(
        "SELECT id, status, metadata FROM videos WHERE id = $1 AND user_id = $2",
        video_id, user_id,
    )
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    if video["status"] != "identifying":
        raise HTTPException(status_code=409, detail=f"Video is in '{video['status']}' state, not 'identifying'")

    import json as _json
    raw_meta = video["metadata"]
    if isinstance(raw_meta, str):
        meta = _json.loads(raw_meta)
    else:
        meta = raw_meta or {}
    frame_key = meta.get("seed_frame_key")
    bboxes = meta.get("player_bboxes", [])

    if not frame_key:
        raise HTTPException(status_code=409, detail="Seed frame not yet extracted")

    frame_url = storage.generate_download_url(frame_key, expires_in=300)
    return {"frame_url": frame_url, "bboxes": bboxes}


@router.post("/videos/{video_id}/identify")
async def tap_identify(
    video_id: str,
    body: TapIdentifyRequest,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
):
    """User taps on their bounding box. Resumes the pipeline."""
    from app.workers.ingest import resume_after_identify  # lazy import

    video = await db.fetchrow(
        "SELECT id, status, metadata FROM videos WHERE id = $1 AND user_id = $2",
        video_id, user_id,
    )
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    if video["status"] != "identifying":
        raise HTTPException(status_code=409, detail="Video is not waiting for identification")

    import json as _json
    raw_meta = video["metadata"]
    meta = _json.loads(raw_meta) if isinstance(raw_meta, str) else (raw_meta or {})
    bboxes = meta.get("player_bboxes", [])
    if body.bbox_index < 0 or body.bbox_index >= len(bboxes):
        raise HTTPException(status_code=422, detail=f"bbox_index must be 0-{len(bboxes)-1}")

    seed_bbox = bboxes[body.bbox_index]

    import json as _json2
    await db.execute(
        """UPDATE videos
           SET status = 'processing',
               identify_started_at = NULL,
               metadata = metadata || $2::jsonb
           WHERE id = $1""",
        video_id, _json2.dumps({"selected_seed_bbox": seed_bbox}),
    )
    resume_after_identify.delay(video_id, user_id, seed_bbox)

    return {"status": "processing"}


@router.post("/videos/{video_id}/confirm-identity")
async def confirm_identity(
    video_id: str,
    body: ConfirmIdentityRequest,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
):
    """
    For the 'confirming' flow: user accepts the auto-selected candidate or falls back to manual tap.
    """
    from app.workers.ingest import resume_after_identify

    video = await db.fetchrow(
        "SELECT id, status, metadata FROM videos WHERE id = $1 AND user_id = $2",
        video_id, user_id,
    )
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    if video["status"] != "confirming":
        raise HTTPException(status_code=409, detail="Video is not waiting for identity confirmation")

    import json as _json
    raw_meta = video["metadata"]
    meta = _json.loads(raw_meta) if isinstance(raw_meta, str) else (raw_meta or {})
    auto_bbox = meta.get("auto_candidate_bbox")
    bboxes = meta.get("player_bboxes", [])

    if body.confirmed and auto_bbox:
        await db.execute("UPDATE videos SET status = 'processing' WHERE id = $1", video_id)
        resume_after_identify.delay(video_id, user_id, auto_bbox)
        return {"status": "processing", "auto_recognized": True}
    else:
        # Fall back to full 4-box tap flow
        await db.execute("UPDATE videos SET status = 'identifying' WHERE id = $1", video_id)
        return {"status": "identifying", "bboxes": bboxes}
