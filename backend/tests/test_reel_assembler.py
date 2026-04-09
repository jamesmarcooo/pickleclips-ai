import os
import tempfile
import numpy as np
import cv2
import pytest
from app.ml.reel_assembler import (
    ClipSpec,
    ReelConfig,
    ReelAssembler,
    smart_crop_frame,
)


def make_test_video(path: str, n_frames: int = 30, fps: int = 30) -> str:
    """Write a minimal MP4 to disk for testing."""
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(path, fourcc, fps, (640, 360))
    for i in range(n_frames):
        frame = np.full((360, 640, 3), i * 8 % 255, dtype=np.uint8)
        out.write(frame)
    out.release()
    return path


def test_smart_crop_horizontal_noop():
    frame = np.zeros((360, 640, 3), dtype=np.uint8)
    cropped = smart_crop_frame(frame, format="horizontal", user_center_x=0.5)
    assert cropped.shape == frame.shape


def test_smart_crop_vertical_returns_9x16_ratio():
    frame = np.zeros((360, 640, 3), dtype=np.uint8)
    cropped = smart_crop_frame(frame, format="vertical", user_center_x=0.5)
    h, w = cropped.shape[:2]
    ratio = h / w
    assert abs(ratio - (16 / 9)) < 0.1


def test_smart_crop_square_returns_1x1_ratio():
    frame = np.zeros((360, 640, 3), dtype=np.uint8)
    cropped = smart_crop_frame(frame, format="square", user_center_x=0.5)
    h, w = cropped.shape[:2]
    assert abs(h - w) <= 2


def test_reel_assembler_init():
    assembler = ReelAssembler(music_dir="backend/static/music")
    assert assembler is not None


def test_clip_spec_dataclass():
    spec = ClipSpec(local_path="/tmp/clip.mp4", highlight_score=0.9, slow_mo_factor=0.5)
    assert spec.slow_mo_factor == 0.5


def test_reel_config_defaults():
    config = ReelConfig(output_type="highlight_montage")
    assert config.format == "horizontal"
    assert config.music_track == "energetic_bg"
