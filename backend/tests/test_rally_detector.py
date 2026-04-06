import pytest
import numpy as np
from app.ml.rally_detector import detect_rallies, compute_frame_motion, Rally


def test_single_rally_detected():
    # 30 frames at 2fps = 15 seconds
    # motion: 5 frames still, 20 frames active, 5 frames still
    motion = [0.05] * 5 + [0.8] * 20 + [0.05] * 5
    rallies = detect_rallies(motion, fps=2, motion_threshold=0.1, min_gap_frames=2)
    assert len(rallies) == 1
    assert rallies[0].start_frame == 5
    assert rallies[0].end_frame == 24


def test_two_rallies_detected():
    # Two active segments separated by a gap
    motion = [0.05] * 3 + [0.8] * 10 + [0.05] * 4 + [0.8] * 10 + [0.05] * 3
    rallies = detect_rallies(motion, fps=2, motion_threshold=0.1, min_gap_frames=2)
    assert len(rallies) == 2


def test_empty_signal_returns_no_rallies():
    rallies = detect_rallies([], fps=2)
    assert rallies == []


def test_rally_to_ms_conversion():
    rally = Rally(start_frame=10, end_frame=20, fps=2)
    assert rally.start_time_ms == 5000   # frame 10 at 2fps = 5 seconds
    assert rally.end_time_ms == 10000    # frame 20 at 2fps = 10 seconds


def test_compute_frame_motion_returns_scalar():
    prev = np.zeros((100, 100, 3), dtype=np.uint8)
    curr = np.zeros((100, 100, 3), dtype=np.uint8)
    curr[40:60, 40:60] = 200  # changed region

    motion = compute_frame_motion(prev, curr)
    assert isinstance(motion, float)
    assert motion > 0.0
