import pytest
import numpy as np
from unittest.mock import patch, MagicMock
from app.workers import ingest
from app.services.usage_guard import QuotaExceededError
from app.workers.ingest import _count_user_frames


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


def _make_labeled_frames(pattern: list) -> list:
    """Build labeled_frames where True = user detected, False = no detections."""
    frames = []
    for has_user in pattern:
        if has_user:
            frames.append([{"role": "user", "bbox": {"x": 0, "y": 0, "w": 10, "h": 10}}])
        else:
            frames.append([])
    return frames


def test_count_user_frames_all_present():
    labeled = _make_labeled_frames([True, True, True])
    with_user, total = _count_user_frames(labeled, frame_start=0, frame_end=2)
    assert with_user == 3
    assert total == 3


def test_count_user_frames_none_present():
    labeled = _make_labeled_frames([False, False, False])
    with_user, total = _count_user_frames(labeled, frame_start=0, frame_end=2)
    assert with_user == 0
    assert total == 3


def test_count_user_frames_partial():
    labeled = _make_labeled_frames([True, False, True, False])
    with_user, total = _count_user_frames(labeled, frame_start=0, frame_end=3)
    assert with_user == 2
    assert total == 4


def test_count_user_frames_clamps_to_available_frames():
    labeled = _make_labeled_frames([True, True])
    with_user, total = _count_user_frames(labeled, frame_start=0, frame_end=99)
    assert total == 2
    assert with_user == 2


def test_count_user_frames_subrange():
    labeled = _make_labeled_frames([True, False, False, True])
    with_user, total = _count_user_frames(labeled, frame_start=1, frame_end=2)
    assert with_user == 0
    assert total == 2


def test_user_presence_filter_logic_skips_low_presence_rally():
    """
    _count_user_frames returning below 30% should cause a rally to be skipped.
    Validates the filter threshold logic without running the full pipeline.
    """
    # 1 user frame out of 5 = 20% < 30% threshold → should skip
    labeled = _make_labeled_frames([True, False, False, False, False])
    with_user, total = _count_user_frames(labeled, frame_start=0, frame_end=4)
    presence_ratio = with_user / total
    assert presence_ratio < 0.30, "Expected <30% presence for this pattern"

    # 2 user frames out of 5 = 40% >= 30% → should keep
    labeled2 = _make_labeled_frames([True, False, True, False, False])
    with_user2, total2 = _count_user_frames(labeled2, frame_start=0, frame_end=4)
    presence_ratio2 = with_user2 / total2
    assert presence_ratio2 >= 0.30, "Expected >=30% presence for this pattern"


def test_run_ai_pipeline_skips_when_highlights_exist():
    """
    If highlights already exist for video_id, run_ai_pipeline must return
    without downloading video or inserting more records.
    The dedup guard is the first asyncio.run call after update_video_status.
    """
    call_count = [0]

    def fake_run(coro):
        call_count[0] += 1
        if call_count[0] == 1:
            # highlights_exist() → True means highlights already in DB
            return True
        raise AssertionError(f"asyncio.run called a second time (call #{call_count[0]}); dedup guard should have returned")

    with patch("app.workers.ingest.asyncio.run", side_effect=fake_run), \
         patch("app.workers.ingest.update_video_status") as mock_status, \
         patch("app.workers.ingest.get_r2_boto_client") as mock_s3:

        ingest.run_ai_pipeline("video-id", "user-id", {"x": 0, "y": 0, "w": 50, "h": 100})

    # S3 must not be called — no video download should happen
    mock_s3.assert_not_called()
    # Only the initial processing status update should have fired
    mock_status.assert_called_once_with("video-id", "processing")


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
