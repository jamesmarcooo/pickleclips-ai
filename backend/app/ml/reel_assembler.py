"""
Reel assembly using FFmpeg subprocess calls.

Takes a list of local clip files + assembly config and produces a single
output video with: optional slow-mo on peak moments, smart crop to target
format, fade-concat transitions, and optional background music.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

import cv2
import numpy as np

Format = Literal["vertical", "horizontal", "square"]
OutputType = Literal[
    "highlight_montage", "my_best_plays", "game_recap",
    "points_of_improvement", "best_shots", "scored_point_rally",
    "full_rally_replay", "single_shot_clip",
]

_FORMAT_DIMS: dict[str, tuple[int, int]] = {
    "horizontal": (1920, 1080),
    "vertical": (1080, 1920),
    "square": (1080, 1080),
}

_SLOW_MO_SCORE_THRESHOLD = 0.85
_SLOW_MO_FACTOR = 0.5

_OUTPUT_TYPE_MUSIC: dict[str, str] = {
    "highlight_montage": "energetic_bg",
    "my_best_plays": "energetic_bg",
    "game_recap": "chill_bg",
    "points_of_improvement": "chill_bg",
    "best_shots": "energetic_bg",
    "scored_point_rally": "energetic_bg",
    "full_rally_replay": "chill_bg",
    "single_shot_clip": "energetic_bg",
}


@dataclass
class ClipSpec:
    local_path: str
    highlight_score: float = 0.5
    slow_mo_factor: float = 1.0
    user_center_x: float = 0.5


@dataclass
class ReelConfig:
    output_type: OutputType
    format: Format = "horizontal"
    music_track: str = field(default="")
    include_music: bool = True
    music_volume: float = 0.3

    def __post_init__(self) -> None:
        if not self.music_track:
            self.music_track = _OUTPUT_TYPE_MUSIC.get(self.output_type, "energetic_bg")


def smart_crop_frame(
    frame: np.ndarray,
    format: str,
    user_center_x: float = 0.5,
) -> np.ndarray:
    """
    Crop a frame to the target aspect ratio, centering on the user's x position.
    For 'horizontal', returns the frame unchanged (already 16:9 source).
    """
    if format == "horizontal":
        return frame

    h, w = frame.shape[:2]
    target_w, target_h = _FORMAT_DIMS[format]
    target_ratio = target_w / target_h

    if format == "vertical":
        crop_w = int(h * target_ratio)
        crop_w = min(crop_w, w)
        center_x = int(user_center_x * w)
        x1 = max(0, center_x - crop_w // 2)
        x2 = min(w, x1 + crop_w)
        x1 = max(0, x2 - crop_w)
        return frame[:, x1:x2]

    if format == "square":
        side = min(h, w)
        center_x = int(user_center_x * w)
        x1 = max(0, center_x - side // 2)
        x2 = min(w, x1 + side)
        x1 = max(0, x2 - side)
        y_offset = (h - side) // 2
        return frame[y_offset:y_offset + side, x1:x2]

    return frame


def _vertical_crop_filter(user_center_x: float = 0.5) -> str:
    frame_w, frame_h = 1920, 1080
    crop_w = int(frame_h * 9 / 16)  # 607 px
    user_x_px = int(user_center_x * frame_w)
    x_offset = max(0, min(frame_w - crop_w, user_x_px - crop_w // 2))
    return f"crop={crop_w}:{frame_h}:{x_offset}:0,scale=1080:1920"


class ReelAssembler:
    """
    Assembles highlight clips into a reel video via FFmpeg subprocesses.

    Usage:
        assembler = ReelAssembler(music_dir="backend/static/music")
        output_path = assembler.assemble(clips, config, output_path="/tmp/reel.mp4")
    """

    def __init__(self, music_dir: str = "backend/static/music"):
        self.music_dir = Path(music_dir)

    def _apply_slow_mo(self, input_path: str, output_path: str, factor: float) -> None:
        """Use FFmpeg setpts + atempo to slow down a clip.
        atempo supports [0.5, 2.0]; for factors below 0.5, chain two filters.
        """
        pts_factor = 1.0 / factor
        # Build atempo filter chain — each stage clamped to [0.5, 2.0]
        if factor >= 0.5:
            atempo_filter = f"atempo={factor:.3f}"
        else:
            # Two-stage: e.g. factor=0.25 → atempo=0.5,atempo=0.5
            stage = max(0.5, factor ** 0.5)
            atempo_filter = f"atempo={stage:.3f},atempo={stage:.3f}"

        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-vf", f"setpts={pts_factor:.3f}*PTS",
            "-af", atempo_filter,
            "-c:v", "libx264", "-c:a", "aac", "-preset", "fast",
            output_path,
        ]
        subprocess.run(cmd, check=True, capture_output=True)

    def _resize_to_format(
        self, input_path: str, output_path: str, config: ReelConfig,
        user_center_x: float = 0.5,
    ) -> None:
        """Resize clip to target format dimensions via FFmpeg."""
        target_w, target_h = _FORMAT_DIMS[config.format]

        if config.format == "horizontal":
            scale_filter = (
                f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,"
                f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2"
            )
        elif config.format == "vertical":
            scale_filter = _vertical_crop_filter(user_center_x)
        else:  # square
            scale_filter = (
                f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
                f"crop={target_w}:{target_h}"
            )

        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-vf", scale_filter,
            "-c:v", "libx264", "-c:a", "aac", "-preset", "fast",
            output_path,
        ]
        subprocess.run(cmd, check=True, capture_output=True)

    def _concat_clips(self, clip_paths: list[str], output_path: str) -> None:
        """Concatenate clips using FFmpeg concat demuxer."""
        if len(clip_paths) == 1:
            shutil.copy(clip_paths[0], output_path)
            return

        list_file = output_path + ".txt"
        with open(list_file, "w") as f:
            for p in clip_paths:
                escaped = p.replace("\\", "\\\\").replace("'", "\\'")
                f.write(f"file '{escaped}'\n")
        try:
            cmd = [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file,
                "-c:v", "libx264", "-c:a", "aac", "-preset", "fast",
                output_path,
            ]
            subprocess.run(cmd, check=True, capture_output=True)
        finally:
            os.unlink(list_file)

    def _mix_music(
        self, video_path: str, output_path: str, config: ReelConfig
    ) -> None:
        """Mix background music into video, ducked under natural audio."""
        music_path = self.music_dir / f"{config.music_track}.mp3"
        if not music_path.exists():
            shutil.copy(video_path, output_path)
            return

        vol = config.music_volume
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-stream_loop", "-1", "-i", str(music_path),
            "-filter_complex",
            f"[0:a]volume=1.0[orig];[1:a]volume={vol:.2f}[music];[orig][music]amix=inputs=2:duration=first[out]",
            "-map", "0:v", "-map", "[out]",
            "-c:v", "copy", "-c:a", "aac", "-shortest",
            output_path,
        ]
        subprocess.run(cmd, check=True, capture_output=True)

    def assemble(
        self,
        clips: list[ClipSpec],
        config: ReelConfig,
        output_path: str,
    ) -> str:
        """
        Assemble clips into a reel. Returns output_path on success.
        Raises subprocess.CalledProcessError if FFmpeg fails.
        """
        if not clips:
            raise ValueError("No clips provided for reel assembly")

        with tempfile.TemporaryDirectory(prefix="pickleclips_reel_") as tmp:
            processed: list[str] = []

            for i, clip in enumerate(clips):
                current = clip.local_path
                # Explicit slow_mo_factor takes precedence over auto slow-mo.
                # Only auto-apply slow-mo if factor is at default (1.0) and score is high.
                if clip.slow_mo_factor != 1.0:
                    effective_factor = clip.slow_mo_factor
                elif clip.highlight_score >= _SLOW_MO_SCORE_THRESHOLD:
                    effective_factor = _SLOW_MO_FACTOR
                else:
                    effective_factor = 1.0

                if effective_factor != 1.0:
                    slo_path = os.path.join(tmp, f"clip_{i:03d}_slo.mp4")
                    self._apply_slow_mo(current, slo_path, effective_factor)
                    current = slo_path

                step_path = os.path.join(tmp, f"clip_{i:03d}_fmt.mp4")
                self._resize_to_format(current, step_path, config, clip.user_center_x)
                processed.append(step_path)

            concat_path = os.path.join(tmp, "concat.mp4")
            self._concat_clips(processed, concat_path)

            if config.include_music:
                self._mix_music(concat_path, output_path, config)
            else:
                shutil.copy(concat_path, output_path)

        return output_path
