import pytest
from app.ml.ball_detection import BallDetection
from app.ml.pose_estimator import PoseKeypoints
from app.ml.shot_classifier import classify_shot, ShotClassification


def _ball(x: float, y: float, conf: float = 0.9) -> BallDetection:
    return BallDetection(frame_idx=0, x=x, y=y, confidence=conf)


def _pose_overhead() -> PoseKeypoints:
    """Wrist above shoulder — smash/overhead setup."""
    return PoseKeypoints(
        left_wrist=(0.3, 0.1, 0.9),
        right_wrist=(0.7, 0.1, 0.9),
        left_elbow=(0.3, 0.3, 0.9),
        right_elbow=(0.7, 0.3, 0.9),
        left_shoulder=(0.3, 0.5, 0.9),
        right_shoulder=(0.7, 0.5, 0.9),
    )


def _pose_low() -> PoseKeypoints:
    """Wrist near waist — dink/drop setup."""
    return PoseKeypoints(
        left_wrist=(0.3, 0.7, 0.9),
        right_wrist=(0.7, 0.7, 0.9),
        left_elbow=(0.3, 0.6, 0.9),
        right_elbow=(0.7, 0.6, 0.9),
        left_shoulder=(0.3, 0.5, 0.9),
        right_shoulder=(0.7, 0.5, 0.9),
    )


def test_classify_overhead_when_speed_low():
    shot = classify_shot(
        ball_before=_ball(0.5, 0.3),
        ball_after=_ball(0.51, 0.45),  # slow descent, speed << _SPEED_HIGH (0.25)
        pose=_pose_overhead(),
        player_crossed_centerline=False,
    )
    assert shot.shot_type == "overhead"


def test_classify_smash_high_wrist_ball_descending():
    shot = classify_shot(
        ball_before=_ball(0.5, 0.3),
        ball_after=_ball(0.6, 0.8),
        pose=_pose_overhead(),
        player_crossed_centerline=False,
    )
    assert shot.shot_type == "smash"


def test_classify_lob_ball_trajectory_steeply_upward():
    shot = classify_shot(
        ball_before=_ball(0.5, 0.8),
        ball_after=_ball(0.5, 0.1),
        pose=_pose_low(),
        player_crossed_centerline=False,
    )
    assert shot.shot_type == "lob"


def test_classify_erne_player_crosses_centerline():
    shot = classify_shot(
        ball_before=_ball(0.5, 0.5),
        ball_after=_ball(0.7, 0.5),
        pose=_pose_low(),
        player_crossed_centerline=True,
    )
    assert shot.shot_type == "erne"


def test_classify_dink_low_pose_ball_near_net():
    shot = classify_shot(
        ball_before=_ball(0.5, 0.55),
        ball_after=_ball(0.55, 0.5),
        pose=_pose_low(),
        player_crossed_centerline=False,
    )
    assert shot.shot_type == "dink"


def test_classify_drive_default_high_speed():
    shot = classify_shot(
        ball_before=_ball(0.2, 0.5),
        ball_after=_ball(0.9, 0.5),
        pose=_pose_low(),
        player_crossed_centerline=False,
    )
    assert shot.shot_type == "drive"


def test_shot_quality_float_in_range():
    shot = classify_shot(
        ball_before=_ball(0.5, 0.5),
        ball_after=_ball(0.6, 0.5),
        pose=_pose_low(),
        player_crossed_centerline=False,
    )
    assert isinstance(shot.quality, float)
    assert 0.0 <= shot.quality <= 1.0


def test_classify_returns_drive_on_no_ball():
    shot = classify_shot(
        ball_before=None,
        ball_after=None,
        pose=None,
        player_crossed_centerline=False,
    )
    assert shot.shot_type == "drive"
    assert shot.quality == 0.5
