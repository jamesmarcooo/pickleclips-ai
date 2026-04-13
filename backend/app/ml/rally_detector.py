from dataclasses import dataclass
import numpy as np
import cv2


@dataclass
class Rally:
    start_frame: int
    end_frame: int
    fps: float

    @property
    def start_time_ms(self) -> int:
        return int((self.start_frame / self.fps) * 1000)

    @property
    def end_time_ms(self) -> int:
        return int((self.end_frame / self.fps) * 1000)

    @property
    def duration_seconds(self) -> float:
        return (self.end_frame - self.start_frame + 1) / self.fps


def compute_frame_motion(prev: np.ndarray, curr: np.ndarray) -> float:
    """
    Compute normalized motion between two consecutive frames.
    Returns a float in [0, 1] where 1 = maximum motion.
    Uses absolute pixel difference of grayscale frames.
    """
    prev_gray = cv2.cvtColor(prev, cv2.COLOR_BGR2GRAY).astype(np.float32)
    curr_gray = cv2.cvtColor(curr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    diff = np.abs(curr_gray - prev_gray)
    return float(diff.mean() / 255.0)


def build_motion_signal(frames: list[np.ndarray]) -> list[float]:
    """Compute per-frame motion signal from a sequence of frames."""
    if len(frames) < 2:
        return [0.0] * len(frames)
    signal = [0.0]  # first frame has no previous
    for i in range(1, len(frames)):
        signal.append(compute_frame_motion(frames[i - 1], frames[i]))
    return signal


def detect_rallies(
    motion_signal: list[float],
    fps: float = 2.0,
    motion_threshold: float = 0.03,
    min_gap_frames: int = 4,
    min_rally_frames: int = 2,
) -> list[Rally]:
    """
    Detect rallies from a per-frame motion signal.

    A rally is a continuous region where motion > motion_threshold.
    Gaps of min_gap_frames or fewer are filled (brief pauses within a rally).
    Rallies shorter than min_rally_frames are discarded (noise).

    Returns list of Rally objects sorted by start_frame.
    """
    if not motion_signal:
        return []

    active = [m > motion_threshold for m in motion_signal]

    # Fill short gaps (brief still moments within a rally)
    i = 0
    while i < len(active):
        if not active[i]:
            gap_start = i
            while i < len(active) and not active[i]:
                i += 1
            gap_length = i - gap_start
            if gap_length <= min_gap_frames:
                for k in range(gap_start, i):
                    active[k] = True
        else:
            i += 1

    # Extract contiguous active segments
    rallies = []
    in_rally = False
    start = 0

    for i, is_active in enumerate(active):
        if is_active and not in_rally:
            in_rally = True
            start = i
        elif not is_active and in_rally:
            in_rally = False
            if (i - start) >= min_rally_frames:
                rallies.append(Rally(start_frame=start, end_frame=i - 1, fps=fps))

    # Close rally at end of signal
    if in_rally and (len(active) - start) >= min_rally_frames:
        rallies.append(Rally(start_frame=start, end_frame=len(active) - 1, fps=fps))

    return rallies
