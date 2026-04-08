"""
Pose estimation using MediaPipe Pose.
Extracts wrist, elbow, and shoulder keypoints from a player crop.
"""
from __future__ import annotations

import math
import numpy as np
from dataclasses import dataclass
from typing import Optional

try:
    import cv2
except ImportError:
    raise ImportError("opencv-python-headless is required: pip install opencv-python-headless")

try:
    import mediapipe as mp
    _mp_pose = mp.solutions.pose
    _mediapipe_available = True
except ImportError:  # pragma: no cover
    _mp_pose = None  # type: ignore[assignment]
    _mediapipe_available = False


@dataclass
class PoseKeypoints:
    """
    Normalized (x, y, visibility) tuples from MediaPipe.
    x, y are in [0, 1] relative to the crop frame.
    """
    left_wrist: tuple[float, float, float]
    right_wrist: tuple[float, float, float]
    left_elbow: tuple[float, float, float]
    right_elbow: tuple[float, float, float]
    left_shoulder: tuple[float, float, float]
    right_shoulder: tuple[float, float, float]


class PoseEstimator:
    """
    Wraps MediaPipe Pose for single-image inference on player crops.
    Run on cropped bounding box of a single player, not the full game frame.
    """

    def __init__(self, model_complexity: int = 1, min_confidence: float = 0.5):
        if not _mediapipe_available:
            raise ImportError(
                "mediapipe is required for PoseEstimator. Install it with: pip install mediapipe"
            )
        self._pose = _mp_pose.Pose(
            static_image_mode=True,
            model_complexity=model_complexity,
            min_detection_confidence=min_confidence,
        )

    def estimate(self, frame_bgr: np.ndarray) -> Optional[PoseKeypoints]:
        """Run pose estimation on a single BGR frame or crop."""
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        result = self._pose.process(rgb)
        if not result.pose_landmarks:
            return None
        lm = result.pose_landmarks.landmark

        def _lm(idx: int) -> tuple[float, float, float]:
            p = lm[idx]
            return (p.x, p.y, p.visibility)

        return PoseKeypoints(
            left_wrist=_lm(_mp_pose.PoseLandmark.LEFT_WRIST),
            right_wrist=_lm(_mp_pose.PoseLandmark.RIGHT_WRIST),
            left_elbow=_lm(_mp_pose.PoseLandmark.LEFT_ELBOW),
            right_elbow=_lm(_mp_pose.PoseLandmark.RIGHT_ELBOW),
            left_shoulder=_lm(_mp_pose.PoseLandmark.LEFT_SHOULDER),
            right_shoulder=_lm(_mp_pose.PoseLandmark.RIGHT_SHOULDER),
        )

    def close(self) -> None:
        self._pose.close()


_VISIBILITY_THRESHOLD = 0.5


def estimate_swing_angle(
    kp: PoseKeypoints, hand: str = "right"
) -> Optional[float]:
    """
    Compute wrist-to-elbow vector angle (degrees, 0° = pointing right).
    Returns None if keypoint visibility is below threshold.
    """
    if hand == "right":
        wrist = kp.right_wrist
        elbow = kp.right_elbow
    else:
        wrist = kp.left_wrist
        elbow = kp.left_elbow

    if wrist[2] < _VISIBILITY_THRESHOLD or elbow[2] < _VISIBILITY_THRESHOLD:
        return None

    dx = wrist[0] - elbow[0]
    dy = wrist[1] - elbow[1]
    return math.degrees(math.atan2(dy, dx))
