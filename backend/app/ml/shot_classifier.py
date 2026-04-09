"""
Rule-based shot classifier for pickleball.

Derives shot type and quality from:
  - Ball trajectory (position before/after contact)
  - Pose keypoints (wrist/elbow angles)
  - Player court position (crossed centerline = erne)

Phase 3 upgrade: replace with VideoMAE/MoViNet classifier trained on
these rule-based labels as weak supervision.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Optional

from app.ml.ball_detection import BallDetection
from app.ml.pose_estimator import PoseKeypoints

ShotType = Literal[
    "drive", "dink", "lob", "erne", "smash", "overhead",
    # Phase 3 stubs — not returned by rule-based classifier yet:
    "drop", "speed_up", "atp",
]

# Thresholds
_NET_Y = 0.5          # normalized y-coord of net (centre of frame)
_SPEED_HIGH = 0.25    # ball displacement per frame above this → fast shot
_SPEED_LOW = 0.08     # below this → soft contact (dink/drop)
_LOB_DY = -0.25       # ball rising steeply (y decreasing, origin top-left)
# Pose keypoints are crop-relative (not full-frame).
# 0.1 was calibrated for a typical tight-body player crop where wrist
# visibly above head equals ~10% of crop height. Adjust if crop sizing changes.
_SMASH_WRIST_ABOVE_SHOULDER_Y = 0.1


@dataclass
class ShotClassification:
    shot_type: ShotType
    quality: float  # 0.0–1.0


def _ball_speed(b1: BallDetection, b2: BallDetection) -> float:
    dx = b2.x - b1.x
    dy = b2.y - b1.y
    return math.sqrt(dx * dx + dy * dy)


def _is_overhead_pose(pose: PoseKeypoints) -> bool:
    """Returns True if the higher-visibility wrist is above shoulder level."""
    for wrist, shoulder in [
        (pose.right_wrist, pose.right_shoulder),
        (pose.left_wrist, pose.left_shoulder),
    ]:
        if wrist[2] > 0.5 and shoulder[2] > 0.5:
            # Smaller y = higher on screen in image coordinates
            if wrist[1] < shoulder[1] - _SMASH_WRIST_ABOVE_SHOULDER_Y:
                return True
    return False


def _shot_quality(
    pose: Optional[PoseKeypoints],
    shot_type: ShotType,
    ball_before: Optional[BallDetection],
    ball_after: Optional[BallDetection],
) -> float:
    """
    Heuristic quality score 0.0–1.0.
    - Pose joint visibility average → form proxy
    - Ball speed relative to shot type → contact quality
    """
    if pose is None:
        return 0.5

    joints = [
        pose.right_wrist, pose.left_wrist,
        pose.right_elbow, pose.left_elbow,
        pose.right_shoulder, pose.left_shoulder,
    ]
    avg_visibility = sum(j[2] for j in joints) / len(joints)
    base = avg_visibility * 0.7

    if ball_before is not None and ball_after is not None:
        speed = _ball_speed(ball_before, ball_after)
        if shot_type in ("drive", "smash", "overhead", "speed_up"):
            speed_bonus = min(speed / _SPEED_HIGH, 1.0) * 0.3
        else:
            speed_bonus = (1.0 - min(speed / _SPEED_HIGH, 1.0)) * 0.3
        return min(base + speed_bonus, 1.0)

    return base


def classify_shot(
    ball_before: Optional[BallDetection],
    ball_after: Optional[BallDetection],
    pose: Optional[PoseKeypoints],
    player_crossed_centerline: bool,
) -> ShotClassification:
    """
    Classify shot type using rule-based logic.

    Priority order (highest specificity first):
    1. Erne — player crosses centerline
    2. Smash/Overhead — overhead pose + ball descending fast
    3. Lob — ball trajectory steeply upward
    4. Dink — soft contact + ball near net height
    5. Drive — default for fast horizontal shots
    """
    # 1. Erne
    if player_crossed_centerline:
        quality = _shot_quality(pose, "erne", ball_before, ball_after)
        return ShotClassification(shot_type="erne", quality=quality)

    # Without ball data, return default
    if ball_before is None or ball_after is None:
        return ShotClassification(shot_type="drive", quality=0.5)

    dy = ball_after.y - ball_before.y  # positive = ball falling
    speed = _ball_speed(ball_before, ball_after)

    # 2. Smash / Overhead
    # Requires pose — if pose unavailable, overhead cannot be confirmed; falls through to drive.
    if pose is not None and _is_overhead_pose(pose) and dy > 0.1:
        shot_type: ShotType = "smash" if speed > _SPEED_HIGH else "overhead"
        quality = _shot_quality(pose, shot_type, ball_before, ball_after)
        return ShotClassification(shot_type=shot_type, quality=quality)

    # 3. Lob
    # Ball must have been hit from mid-to-back court (y > 0.35) to be a lob.
    # A steeply-rising ball near the net is more likely a high dink or sensor artifact.
    if dy < _LOB_DY and ball_before.y > 0.35:
        quality = _shot_quality(pose, "lob", ball_before, ball_after)
        return ShotClassification(shot_type="lob", quality=quality)

    # 4. Dink
    if speed < _SPEED_LOW and ball_before.y > _NET_Y - 0.1:
        quality = _shot_quality(pose, "dink", ball_before, ball_after)
        return ShotClassification(shot_type="dink", quality=quality)

    # 5. Drive (default)
    quality = _shot_quality(pose, "drive", ball_before, ball_after)
    return ShotClassification(shot_type="drive", quality=quality)
