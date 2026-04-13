import logging
import numpy as np
import pytest
from app.ml.ball_detection import BallDetection, BallDetector


def make_frames(n: int, h: int = 288, w: int = 512) -> list:
    """Generate n random uint8 BGR frames at (h, w, 3)."""
    return [np.random.randint(0, 255, (h, w, 3), dtype=np.uint8) for _ in range(n)]


def test_ball_detection_returns_one_result_per_frame():
    detector = BallDetector(weights_path=None)  # CPU, no weights → random heatmap
    frames = make_frames(5)
    results = detector.detect_sequence(frames)
    assert len(results) == 5


def test_ball_detection_result_type():
    detector = BallDetector(weights_path=None)
    frames = make_frames(3)
    results = detector.detect_sequence(frames)
    for r in results:
        assert r is None or isinstance(r, BallDetection)


def test_ball_detection_normalised_coords():
    detector = BallDetector(weights_path=None)
    frames = make_frames(3)
    results = detector.detect_sequence(frames)
    for r in results:
        if r is not None:
            assert 0.0 <= r.x <= 1.0
            assert 0.0 <= r.y <= 1.0
            assert 0.0 <= r.confidence <= 1.0


def test_ball_detector_warns_when_no_weights(caplog):
    """BallDetector must emit a WARNING when weights_path is None."""
    with caplog.at_level(logging.WARNING, logger="app.ml.ball_detection"):
        BallDetector(weights_path=None)
    assert any("random weights" in record.message for record in caplog.records), (
        "Expected a warning mentioning 'random weights' but got: "
        + str([r.message for r in caplog.records])
    )


def test_ball_detector_warns_when_weights_file_missing(tmp_path, caplog):
    """BallDetector must emit a WARNING when weights_path points to a missing file."""
    missing = str(tmp_path / "does_not_exist.pt")
    with caplog.at_level(logging.WARNING, logger="app.ml.ball_detection"):
        BallDetector(weights_path=missing)
    assert any("random weights" in record.message for record in caplog.records), (
        "Expected a warning mentioning 'random weights' but got: "
        + str([r.message for r in caplog.records])
    )


def test_ball_detector_no_warning_when_weights_exist(tmp_path, caplog):
    """BallDetector must NOT warn when a weights file exists."""
    import torch
    weights_file = tmp_path / "weights.pt"
    torch.save({}, str(weights_file))
    with caplog.at_level(logging.WARNING, logger="app.ml.ball_detection"):
        try:
            BallDetector(weights_path=str(weights_file))
        except Exception:
            pass  # load_state_dict may raise on empty dict — fine for this test
    assert not any("random weights" in record.message for record in caplog.records), (
        "Unexpected 'random weights' warning when valid weights file exists"
    )


def test_ball_trajectory_from_detections():
    from app.ml.ball_detection import ball_trajectory_from_detections
    detections = [
        BallDetection(frame_idx=0, x=0.5, y=0.5, confidence=0.9),
        None,
        BallDetection(frame_idx=2, x=0.6, y=0.4, confidence=0.8),
    ]
    traj = ball_trajectory_from_detections(detections, fps=2)
    assert len(traj) == 3
    # interpolated frame 1 should be between frame 0 and frame 2
    if traj[1] is not None:
        assert 0.5 <= traj[1].x <= 0.6
