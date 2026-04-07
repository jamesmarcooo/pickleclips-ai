"""
Ball detection using TrackNetV2.
If weights_path is None (local dev), model runs with random weights — useful for pipeline testing.
"""
from __future__ import annotations

import numpy as np
import cv2
import torch
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.ml.tracknetv2.model import TrackNetV2

_INPUT_H = 288
_INPUT_W = 512
_CONFIDENCE_THRESHOLD = 0.5


@dataclass
class BallDetection:
    frame_idx: int
    x: float         # normalized [0, 1] from left
    y: float         # normalized [0, 1] from top
    confidence: float


class BallDetector:
    def __init__(self, weights_path: str | None, device: str | None = None):
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = torch.device(device)
        self.model = TrackNetV2().to(self.device).eval()
        if weights_path and Path(weights_path).exists():
            state = torch.load(weights_path, map_location=self.device)
            self.model.load_state_dict(state)

    def _preprocess_triplet(self, frames: list[np.ndarray]) -> torch.Tensor:
        channels = []
        for frame in frames:
            resized = cv2.resize(frame, (_INPUT_W, _INPUT_H))
            rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
            channels.append(rgb.transpose(2, 0, 1))
        stacked = np.concatenate(channels, axis=0)
        return torch.from_numpy(stacked).unsqueeze(0).to(self.device)

    def _heatmap_to_detection(
        self, heatmap: np.ndarray, frame_idx: int, orig_h: int, orig_w: int
    ) -> Optional[BallDetection]:
        confidence = float(heatmap.max())
        if confidence < _CONFIDENCE_THRESHOLD:
            return None
        hy, hx = np.unravel_index(heatmap.argmax(), heatmap.shape)
        return BallDetection(
            frame_idx=frame_idx,
            x=float(hx) / heatmap.shape[1],
            y=float(hy) / heatmap.shape[0],
            confidence=confidence,
        )

    def detect_sequence(self, frames: list[np.ndarray]) -> list[Optional[BallDetection]]:
        n = len(frames)
        results: list[Optional[BallDetection]] = [None] * n
        if n < 3:
            return results
        orig_h, orig_w = frames[0].shape[:2]
        with torch.no_grad():
            for i in range(1, n - 1):
                triplet = [frames[i - 1], frames[i], frames[i + 1]]
                inp = self._preprocess_triplet(triplet)
                heatmaps = self.model(inp).squeeze(0).cpu().numpy()
                results[i] = self._heatmap_to_detection(
                    heatmaps[1], frame_idx=i, orig_h=orig_h, orig_w=orig_w
                )
        return results


def ball_trajectory_from_detections(
    detections: list[Optional[BallDetection]],
    fps: float,
) -> list[Optional[BallDetection]]:
    """Linear interpolation over None gaps (max 0.5s gap)."""
    result = list(detections)
    n = len(result)
    max_gap = int(fps * 0.5)
    i = 0
    while i < n:
        if result[i] is None:
            gap_start = i - 1
            gap_end = i
            while gap_end < n and result[gap_end] is None:
                gap_end += 1
            gap_len = gap_end - (gap_start + 1)
            if gap_start >= 0 and gap_end < n and gap_len <= max_gap:
                a = result[gap_start]
                b = result[gap_end]
                for j in range(1, gap_len + 1):
                    t = j / (gap_len + 1)
                    result[gap_start + j] = BallDetection(
                        frame_idx=gap_start + j,
                        x=a.x + t * (b.x - a.x),
                        y=a.y + t * (b.y - a.y),
                        confidence=min(a.confidence, b.confidence) * 0.7,
                    )
            i = gap_end
        else:
            i += 1
    return result
