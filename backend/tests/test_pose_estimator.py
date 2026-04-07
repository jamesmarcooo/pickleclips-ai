import numpy as np
import pytest
from app.ml.pose_estimator import PoseEstimator, PoseKeypoints, estimate_swing_angle


def make_frame(h: int = 480, w: int = 320) -> np.ndarray:
    return np.zeros((h, w, 3), dtype=np.uint8)


def test_pose_estimator_returns_none_on_blank_frame():
    estimator = PoseEstimator()
    frame = make_frame()
    result = estimator.estimate(frame)
    assert result is None or isinstance(result, PoseKeypoints)


def test_pose_keypoints_has_required_joints():
    kp = PoseKeypoints(
        left_wrist=(0.5, 0.3, 0.9),
        right_wrist=(0.6, 0.3, 0.8),
        left_elbow=(0.5, 0.5, 0.9),
        right_elbow=(0.6, 0.5, 0.85),
        left_shoulder=(0.4, 0.6, 0.95),
        right_shoulder=(0.65, 0.6, 0.9),
    )
    assert len(kp.left_wrist) == 3  # (x, y, visibility)
    assert len(kp.right_wrist) == 3


def test_swing_angle_right_arm():
    kp = PoseKeypoints(
        left_wrist=(0.3, 0.2, 0.9),
        right_wrist=(0.7, 0.1, 0.9),
        left_elbow=(0.3, 0.5, 0.9),
        right_elbow=(0.65, 0.4, 0.9),
        left_shoulder=(0.3, 0.6, 0.9),
        right_shoulder=(0.65, 0.6, 0.9),
    )
    angle = estimate_swing_angle(kp, hand="right")
    assert isinstance(angle, float)
    assert -180.0 <= angle <= 180.0


def test_swing_angle_returns_none_on_low_visibility():
    kp = PoseKeypoints(
        left_wrist=(0.3, 0.2, 0.1),
        right_wrist=(0.7, 0.1, 0.1),
        left_elbow=(0.3, 0.5, 0.1),
        right_elbow=(0.65, 0.4, 0.1),
        left_shoulder=(0.3, 0.6, 0.1),
        right_shoulder=(0.65, 0.6, 0.1),
    )
    angle = estimate_swing_angle(kp, hand="right")
    assert angle is None
