import json
import asyncio
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List

import asyncpg
import boto3
import cv2
import ffmpeg
import numpy as np
from botocore.config import Config

from app.workers.celery_app import celery
from app.config import settings


# ── Helpers ───────────────────────────────────────────────────────────────────

def update_video_status(video_id: str, status: str, metadata_update: dict = None) -> None:
    """Sync DB update (run in Celery worker thread)."""
    async def _update():
        conn = await asyncpg.connect(settings.database_url)
        try:
            if metadata_update:
                await conn.execute(
                    """UPDATE videos
                       SET status = $1,
                           metadata = metadata || $2::jsonb
                       WHERE id = $3""",
                    status, json.dumps(metadata_update), video_id,
                )
            else:
                await conn.execute("UPDATE videos SET status = $1 WHERE id = $2", status, video_id)
        finally:
            await conn.close()

    asyncio.run(_update())


def get_r2_boto_client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def transcode_to_1080p(input_path: str, output_path: str) -> None:
    """Transcode video to H.264 1080p working copy using FFmpeg NVENC (GPU)."""
    (
        ffmpeg
        .input(input_path)
        .output(
            output_path,
            vcodec="h264_nvenc",
            acodec="aac",
            vf="scale=-2:1080",
            preset="fast",
            crf=23,
        )
        .overwrite_output()
        .run(capture_stdout=True, capture_stderr=True)
    )


def extract_frames(video_path: str, fps: int = 2) -> List[np.ndarray]:
    """Extract frames at `fps` frames per second from a video file."""
    cap = cv2.VideoCapture(video_path)
    source_fps = cap.get(cv2.CAP_PROP_FPS)
    if source_fps <= 0:
        source_fps = 30.0

    step = max(1, int(source_fps / fps))
    frames = []
    frame_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % step == 0:
            frames.append(frame)
        frame_idx += 1

    cap.release()
    return frames


def pick_seed_frame(frames: List[np.ndarray]) -> np.ndarray:
    """Pick a representative mid-game frame (avoid first/last 10% which may be setup)."""
    start = max(0, len(frames) // 10)
    end = len(frames) - start
    mid = (start + end) // 2
    return frames[mid]


# ── Pipeline tasks ─────────────────────────────────────────────────────────────

@celery.task(bind=True, name="app.workers.ingest.ingest_video", max_retries=3)
def ingest_video(self, video_id: str, user_id: str):
    """
    Stage 1 of the pipeline. Runs before user tap.
    1. Download original from R2 to /tmp
    2. Transcode to 1080p working copy
    3. Extract frames at 2fps
    4. Run YOLOv8n person detection on seed frame
    5. Save bboxes + pause for user tap (status → 'identifying')
    """
    from app.ml.person_detection import detect_players

    tmp_dir = Path(f"/tmp/pickleclips/{video_id}")
    tmp_dir.mkdir(parents=True, exist_ok=True)

    original_path = str(tmp_dir / "original.mp4")
    processed_path = str(tmp_dir / "processed_1080p.mp4")
    seed_frame_path = str(tmp_dir / "seed_frame.jpg")

    try:
        # 1. Fetch R2 key from DB
        async def get_r2_key():
            conn = await asyncpg.connect(settings.database_url)
            try:
                row = await conn.fetchrow("SELECT r2_key_original FROM videos WHERE id = $1", video_id)
                return row["r2_key_original"] if row else None
            finally:
                await conn.close()

        r2_key = asyncio.run(get_r2_key())
        if not r2_key:
            raise ValueError(f"No R2 key for video {video_id}")

        # 2. Download from R2
        s3 = get_r2_boto_client()
        s3.download_file(settings.r2_bucket_name, r2_key, original_path)

        # 3. Transcode to 1080p (GPU; CPU fallback for local dev)
        try:
            transcode_to_1080p(original_path, processed_path)
        except ffmpeg.Error:
            (
                ffmpeg.input(original_path)
                .output(processed_path, vcodec="libx264", acodec="aac", vf="scale=-2:1080", preset="fast")
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )

        # 4. Extract frames
        frames = extract_frames(processed_path, fps=2)
        if not frames:
            raise ValueError("No frames extracted from video")

        # 5. Run person detection on seed frame
        seed_frame = pick_seed_frame(frames)
        cv2.imwrite(seed_frame_path, seed_frame)
        bboxes = detect_players(seed_frame)

        # 6. Upload seed frame to R2
        seed_frame_key = f"videos/{video_id}/seed_frame.jpg"
        s3.upload_file(seed_frame_path, settings.r2_bucket_name, seed_frame_key)

        # 7. Upload processed video to R2
        processed_key = f"videos/{video_id}/processed_1080p.mp4"
        s3.upload_file(processed_path, settings.r2_bucket_name, processed_key)

        # 8. Update DB: status → identifying
        async def save_results():
            conn = await asyncpg.connect(settings.database_url)
            try:
                deadline = datetime.now(timezone.utc) + timedelta(hours=24)
                await conn.execute(
                    """UPDATE videos SET
                        status = 'identifying',
                        r2_key_processed = $1,
                        identify_started_at = NOW(),
                        cleanup_after = $2,
                        metadata = metadata || $3::jsonb
                       WHERE id = $4""",
                    processed_key,
                    deadline,
                    json.dumps({"seed_frame_key": seed_frame_key, "player_bboxes": bboxes}),
                    video_id,
                )
            finally:
                await conn.close()

        asyncio.run(save_results())

    except Exception as exc:
        update_video_status(video_id, "failed")
        raise self.retry(exc=exc, countdown=60)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@celery.task(bind=True, name="app.workers.ingest.resume_after_identify", max_retries=3)
def resume_after_identify(self, video_id: str, user_id: str, seed_bbox: dict):
    """
    Stage 2 of the pipeline. Runs after user tap.
    Delegates to the Re-ID + scoring tasks (implemented in Task 15).
    """
    run_ai_pipeline.delay(video_id, user_id, seed_bbox)


@celery.task(bind=True, name="app.workers.ingest.run_ai_pipeline", max_retries=2)
def run_ai_pipeline(self, video_id: str, user_id: str, seed_bbox: dict):
    """Full AI pipeline: Re-ID → rally detection → scoring → clip extraction."""
    # Implemented in Task 15
    raise NotImplementedError("Implemented in Task 15")
