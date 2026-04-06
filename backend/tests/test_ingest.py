import pytest
import numpy as np
from unittest.mock import patch, MagicMock
from app.workers import ingest


def test_extract_frames_returns_correct_count():
    """extract_frames should return ~2 frames per second of video."""
    mock_cap = MagicMock()
    mock_cap.get.side_effect = lambda prop: {
        7: 1800,   # CAP_PROP_FRAME_COUNT = 1800 frames
        5: 30.0,   # CAP_PROP_FPS = 30 fps = 60 seconds
    }.get(prop, 0)
    mock_cap.read.side_effect = (
        [(True, np.zeros((1080, 1920, 3), dtype=np.uint8))] * 1800 +
        [(False, None)]
    )

    with patch("cv2.VideoCapture", return_value=mock_cap):
        frames = ingest.extract_frames("/fake/path.mp4", fps=2)

    # 60 seconds * 2 fps = 120 frames (±2 for rounding)
    assert 118 <= len(frames) <= 122
    assert isinstance(frames[0], np.ndarray)
