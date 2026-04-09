"""
Reel service — clip selection, assembly orchestration, R2 upload, share URL generation.
Called by reel_gen Celery worker.
"""
from __future__ import annotations

import os
import secrets
import tempfile
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config

from app.config import settings
from app.ml.reel_assembler import ClipSpec, ReelAssembler, ReelConfig

_MAX_CLIPS_PER_REEL = 10
_MAX_GAME_RECAP_CLIPS = 20


def select_clips_for_output_type(
    output_type: str,
    highlights: list[dict],
    lowlights: list[dict],
) -> list[dict]:
    """
    Select and order highlights/lowlights for a given output type.
    Returns a list of highlight dicts with r2_key_clip set.
    """
    available = [h for h in highlights if h.get("r2_key_clip")]

    if output_type == "highlight_montage":
        sorted_h = sorted(available, key=lambda h: h["highlight_score"], reverse=True)
        return sorted_h[:_MAX_CLIPS_PER_REEL]

    if output_type == "my_best_plays":
        user_clips = [h for h in available if h.get("attributed_player_role") == "user"]
        sorted_h = sorted(user_clips, key=lambda h: h["highlight_score"], reverse=True)
        return sorted_h[:_MAX_CLIPS_PER_REEL]

    if output_type == "game_recap":
        scored = [h for h in available if h.get("sub_highlight_type") == "point_scored"]
        # chronological order for game recap
        return sorted(scored, key=lambda h: h.get("start_time_ms", 0))[:_MAX_GAME_RECAP_CLIPS]

    if output_type == "points_of_improvement":
        available_low = [l for l in lowlights if l.get("r2_key_clip")]
        return sorted(available_low, key=lambda h: h.get("shot_quality", 0.5))[:_MAX_CLIPS_PER_REEL]

    if output_type == "best_shots":
        sorted_h = sorted(available, key=lambda h: h.get("shot_quality", 0.5), reverse=True)
        return sorted_h[:_MAX_CLIPS_PER_REEL]

    if output_type in ("scored_point_rally", "full_rally_replay"):
        scored = [h for h in available if h.get("sub_highlight_type") == "point_scored"]
        sorted_h = sorted(scored, key=lambda h: h["highlight_score"], reverse=True)
        return sorted_h[:1]

    if output_type == "single_shot_clip":
        sorted_h = sorted(available, key=lambda h: h["highlight_score"], reverse=True)
        return sorted_h[:1]

    return sorted(available, key=lambda h: h["highlight_score"], reverse=True)[:_MAX_CLIPS_PER_REEL]


def _get_r2_client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def download_clips(clips: list[dict], tmp_dir: str) -> list[tuple[dict, str]]:
    """Download clip files from R2 to tmp_dir. Returns [(highlight, local_path)]."""
    s3 = _get_r2_client()
    downloaded = []
    for clip in clips:
        r2_key = clip["r2_key_clip"]
        local_path = os.path.join(tmp_dir, Path(r2_key).name)
        s3.download_file(settings.r2_bucket_name, r2_key, local_path)
        downloaded.append((clip, local_path))
    return downloaded


def assemble_and_upload(
    reel_id: str,
    output_type: str,
    clips: list[dict],
    lowlights: list[dict],
    format: str = "horizontal",
    user_center_x: float = 0.5,
    music_dir: str = "backend/static/music",
) -> str:
    """
    Full pipeline: select clips → download from R2 → assemble → upload to R2.
    Returns the R2 key of the uploaded reel.
    """
    selected = select_clips_for_output_type(output_type, clips, lowlights)
    if not selected:
        raise ValueError(f"No clips available for output_type={output_type!r}")

    assembler = ReelAssembler(music_dir=music_dir)
    config = ReelConfig(output_type=output_type, format=format)  # type: ignore[arg-type]

    with tempfile.TemporaryDirectory(prefix=f"pickleclips_reel_{reel_id}_") as tmp:
        downloaded = download_clips(selected, tmp)

        clip_specs = [
            ClipSpec(
                local_path=local_path,
                highlight_score=clip.get("highlight_score", 0.5),
                user_center_x=user_center_x,
            )
            for clip, local_path in downloaded
        ]

        output_path = os.path.join(tmp, f"reel_{reel_id}.mp4")
        assembler.assemble(clip_specs, config, output_path)

        r2_key = f"reels/{reel_id}/output_{format}.mp4"
        s3 = _get_r2_client()
        s3.upload_file(output_path, settings.r2_bucket_name, r2_key)

    return r2_key


def generate_share_token() -> str:
    return secrets.token_urlsafe(16)


def generate_share_url(share_token: str) -> str:
    base = settings.app_base_url.rstrip("/")
    return f"{base}/reels/share/{share_token}"
