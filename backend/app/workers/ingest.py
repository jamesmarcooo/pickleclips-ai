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

def _mediapipe_available() -> bool:
    try:
        import mediapipe  # noqa: F401
        return True
    except ImportError:
        return False


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
            cq=23,
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
        # Normalize bbox values to plain Python types for JSON serialization
        bboxes = [
            {k: float(v) if hasattr(v, "item") else v for k, v in bbox.items()}
            for bbox in bboxes
        ]

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
        if self.request.retries >= self.max_retries:
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
    """
    Full AI pipeline after user tap:
    1. Download processed 1080p video + original 2.7K
    2. Extract frames
    3. Run Re-ID tracking across all frames
    4. Run rally detection
    5. Score each rally as highlight
    6. Extract clips from 2.7K original
    7. Upload clips to R2
    8. Write highlights + rallies to DB
    9. Update video status → analyzed
    """
    import uuid
    from app.ml.reid_tracking import extract_embedding, track_user_across_frames
    from app.ml.rally_detector import build_motion_signal, detect_rallies, Rally
    from app.ml.score_state_machine import ScoreStateMachine
    from app.ml.highlight_scorer import score_highlight, is_lowlight
    from app.ml.clip_extractor import ClipSpec, extract_clips_batch
    from app.ml.person_detection import detect_players
    from app.ml.shot_classifier import classify_shot

    tmp_dir = Path(f"/tmp/pickleclips/{video_id}")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    processed_path = str(tmp_dir / "processed_1080p.mp4")
    original_path = str(tmp_dir / "original.mp4")

    try:
        update_video_status(video_id, "processing")

        async def get_video():
            conn = await asyncpg.connect(settings.database_url)
            try:
                return await conn.fetchrow(
                    "SELECT r2_key_original, r2_key_processed FROM videos WHERE id = $1", video_id
                )
            finally:
                await conn.close()

        video = asyncio.run(get_video())
        if video is None:
            raise ValueError(f"No video record found for {video_id}")

        s3 = get_r2_boto_client()

        # Download 1080p working copy for frame extraction
        s3.download_file(settings.r2_bucket_name, video["r2_key_processed"], processed_path)
        # Download original for clip extraction
        s3.download_file(settings.r2_bucket_name, video["r2_key_original"], original_path)

        # Extract frames at 2fps from 1080p working copy
        frames = extract_frames(processed_path, fps=2)

        # Detect players in each frame
        all_detections = [
            [{"bbox": b} for b in detect_players(f)]
            for f in frames
        ]

        # Extract seed embedding from the user-tapped bbox on the seed frame
        seed_frame = pick_seed_frame(frames)
        seed_embedding = extract_embedding(seed_frame, seed_bbox)

        # Track user across all frames
        labeled_frames = track_user_across_frames(frames, all_detections, seed_embedding)

        # ── Phase 2: Ball Detection ─────────────────────────────────────────
        from app.ml.ball_detection import BallDetector, ball_trajectory_from_detections
        ball_detector = BallDetector(weights_path=settings.tracknetv2_weights_path)
        raw_ball_detections = ball_detector.detect_sequence(frames)
        ball_detections = ball_trajectory_from_detections(raw_ball_detections, fps=2)

        # ── Phase 2: Pose Estimation ────────────────────────────────────────
        from app.ml.pose_estimator import PoseEstimator
        pose_estimator = PoseEstimator() if _mediapipe_available() else None
        frame_poses = []
        for frame_i, (frame, labeled) in enumerate(zip(frames, labeled_frames)):
            if pose_estimator is None:
                frame_poses.append(None)
                continue
            user_bbox = next(
                (d["bbox"] for d in labeled if d.get("role") == "user"), None
            )
            if user_bbox:
                x, y, w, h = (
                    int(user_bbox.get("x", 0)), int(user_bbox.get("y", 0)),
                    int(user_bbox.get("w", 100)), int(user_bbox.get("h", 100)),
                )
                crop = frame[max(0, y):y + h, max(0, x):x + w]
                pose = pose_estimator.estimate(crop) if crop.size > 0 else None
            else:
                pose = None
            frame_poses.append(pose)
        if pose_estimator is not None:
            pose_estimator.close()

        # Build motion signal + detect rallies
        motion_signal = build_motion_signal(frames)
        rallies: list[Rally] = detect_rallies(motion_signal, fps=2)

        sm = ScoreStateMachine()
        rally_records = []
        highlight_records = []

        for rally in rallies:
            score_before = sm.get_state().copy()
            rally_id = str(uuid.uuid4())
            rally_record = {
                "id": rally_id,
                "video_id": video_id,
                "start_time_ms": rally.start_time_ms,
                "end_time_ms": rally.end_time_ms,
                "shot_count": max(1, int(rally.duration_seconds * 1.5)),
                "intensity_score": min(rally.duration_seconds / 30.0, 1.0),
                "point_won_by": None,
                "score_before": json.dumps(score_before),
                "score_after": json.dumps(score_before),
                "is_comeback_point": False,
            }
            rally_records.append(rally_record)

            # Get ball and pose at rally midpoint for shot classification
            fps = 2
            rally_frame_start = max(0, rally.start_time_ms * fps // 1000)
            rally_frame_end = min(len(frames) - 1, rally.end_time_ms * fps // 1000)
            mid_frame = (rally_frame_start + rally_frame_end) // 2

            ball_before = ball_detections[mid_frame - 1] if mid_frame > 0 else None
            ball_after = ball_detections[mid_frame + 1] if mid_frame + 1 < len(ball_detections) else None
            pose = frame_poses[mid_frame] if mid_frame < len(frame_poses) else None

            user_positions_x = [
                d["bbox"].get("x", 0) / max(frames[0].shape[1], 1)
                for fi in range(rally_frame_start, rally_frame_end + 1)
                if fi < len(labeled_frames)
                for d in labeled_frames[fi]
                if d.get("role") == "user" and "bbox" in d
            ]
            player_crossed = (
                len(user_positions_x) > 1
                and max(user_positions_x) > 0.5
                and min(user_positions_x) < 0.4
            )

            shot_result = classify_shot(
                ball_before=ball_before,
                ball_after=ball_after,
                pose=pose,
                player_crossed_centerline=player_crossed,
            )

            raw_score = score_highlight(
                point_scored=False,
                point_won_by=None,
                rally_length=rally_record["shot_count"],
                attributed_role="user",
                shot_type=shot_result.shot_type,
                shot_quality=shot_result.quality,
            )
            if rally.duration_seconds > 10:
                raw_score = min(raw_score * 1.3, 1.0)

            lowlight = is_lowlight(shot_quality=shot_result.quality, point_lost_by_error=False)
            sub_type = "lowlight" if lowlight else "point_scored"

            clip_start_ms = max(0, rally.start_time_ms - 1000)
            clip_end_ms = rally.end_time_ms + 1000
            highlight_id = str(uuid.uuid4())
            highlight_records.append({
                "id": highlight_id,
                "video_id": video_id,
                "rally_id": rally_id,
                "attributed_player_role": "user",
                "sub_highlight_type": sub_type,
                "lowlight_type": None,
                "point_lost_by_error": False,
                "start_time_ms": clip_start_ms,
                "end_time_ms": clip_end_ms,
                "highlight_score": raw_score,
                "highlight_score_raw": raw_score,
                "shot_type": shot_result.shot_type,
                "shot_quality": shot_result.quality,
                "point_scored": False,
                "point_won_by": None,
                "rally_length": rally_record["shot_count"],
                "rally_intensity": rally_record["intensity_score"],
                "score_source": "rule_based",
                "r2_key_clip": None,
            })

        # Extract top 15 clips from original 2.7K
        top_highlights = sorted(highlight_records, key=lambda h: h["highlight_score"], reverse=True)[:15]
        clip_specs = []
        for h in top_highlights:
            clip_path = str(tmp_dir / f"clip_{h['id'][:8]}.mp4")
            clip_specs.append(ClipSpec(
                source_path=original_path,
                output_path=clip_path,
                start_ms=h["start_time_ms"],
                end_ms=h["end_time_ms"],
            ))

        successful_paths = extract_clips_batch(clip_specs)

        # Upload clips to R2; build explicit id→key map (avoid mutating shared dicts)
        clip_keys: dict[str, str] = {}
        for i, spec in enumerate(clip_specs):
            if spec.output_path in successful_paths:
                highlight_id = top_highlights[i]["id"]
                r2_key = f"videos/{video_id}/clips/{highlight_id}.mp4"
                s3.upload_file(spec.output_path, settings.r2_bucket_name, r2_key)
                clip_keys[highlight_id] = r2_key

        # Write all records to DB
        async def save_to_db():
            conn = await asyncpg.connect(settings.database_url)
            try:
                async with conn.transaction():
                    for r in rally_records:
                        await conn.execute(
                            """INSERT INTO rallies (id, video_id, start_time_ms, end_time_ms,
                               shot_count, intensity_score, point_won_by, score_before, score_after, is_comeback_point)
                               VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9::jsonb,$10)""",
                            r["id"], r["video_id"], r["start_time_ms"], r["end_time_ms"],
                            r["shot_count"], r["intensity_score"], r["point_won_by"],
                            r["score_before"], r["score_after"], r["is_comeback_point"],
                        )
                    for h in highlight_records:
                        await conn.execute(
                            """INSERT INTO highlights (id, video_id, rally_id, attributed_player_role,
                               sub_highlight_type, lowlight_type, point_lost_by_error,
                               start_time_ms, end_time_ms, highlight_score, highlight_score_raw,
                               shot_type, shot_quality, point_scored, point_won_by, rally_length, rally_intensity,
                               score_source, r2_key_clip)
                               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19)""",
                            h["id"], h["video_id"], h["rally_id"], h["attributed_player_role"],
                            h["sub_highlight_type"], h["lowlight_type"], h["point_lost_by_error"],
                            h["start_time_ms"], h["end_time_ms"], h["highlight_score"], h["highlight_score_raw"],
                            h["shot_type"], h["shot_quality"], h["point_scored"], h["point_won_by"],
                            h["rally_length"], h["rally_intensity"], h["score_source"], clip_keys.get(h["id"]),
                        )
                    await conn.execute(
                        "UPDATE videos SET status = 'analyzed' WHERE id = $1", video_id
                    )
            finally:
                await conn.close()

        asyncio.run(save_to_db())

        # Trigger Phase 2 auto-generated reels
        from app.workers.reel_gen import trigger_auto_generated_reels
        trigger_auto_generated_reels(video_id=video_id, user_id=user_id)

    except Exception as exc:
        if self.request.retries >= self.max_retries:
            update_video_status(video_id, "failed")
        raise self.retry(exc=exc, countdown=120)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
