import pytest
import numpy as np
from unittest.mock import patch, MagicMock
from app.workers import ingest
from app.services.usage_guard import QuotaExceededError


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


def test_ingest_quota_gate_blocks_when_over_limit():
    """When quota check raises QuotaExceededError, video is marked failed."""
    with patch("app.workers.ingest.asyncio.run", side_effect=QuotaExceededError("R2 at 95%")), \
         patch("app.workers.ingest.update_video_status") as mock_update:
        ingest.ingest_video("fake-video-id", "fake-user-id")

    mock_update.assert_called_once()
    call_args = mock_update.call_args[0]
    assert call_args[0] == "fake-video-id"
    assert call_args[1] == "failed"


def test_ingest_quota_gate_passes_when_under_limit():
    """When quota check passes, video is not immediately marked failed."""
    call_count = [0]

    def run_side_effect(coro):
        call_count[0] += 1
        if call_count[0] == 1:
            return None  # quota check passes
        raise StopIteration("stop here")  # stop further execution

    with patch("app.workers.ingest.asyncio.run", side_effect=run_side_effect), \
         patch("app.workers.ingest.update_video_status") as mock_update:
        try:
            ingest.ingest_video("fake-video-id", "fake-user-id")
        except StopIteration:
            pass

    # Video should NOT have been marked failed by the quota gate
    for call in mock_update.call_args_list:
        assert call[0][1] != "failed", "quota gate incorrectly marked video as failed"
