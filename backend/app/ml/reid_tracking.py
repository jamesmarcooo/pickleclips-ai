from enum import Enum
from typing import TypedDict
import numpy as np
import cv2

# torchreid is installed from source; import lazily to avoid import errors on non-GPU machines
_extractor = None


class PlayerRole(str, Enum):
    USER = "user"
    PARTNER = "partner"
    OPPONENT_1 = "opponent_1"
    OPPONENT_2 = "opponent_2"


ROLE_ORDER = [PlayerRole.USER, PlayerRole.PARTNER, PlayerRole.OPPONENT_1, PlayerRole.OPPONENT_2]


def _get_extractor():
    global _extractor
    if _extractor is None:
        import torchreid
        _extractor = torchreid.utils.FeatureExtractor(
            model_name="osnet_x1_0",
            device="cuda" if _cuda_available() else "cpu",
        )
    return _extractor


def _cuda_available() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


def extract_embedding(frame: np.ndarray, bbox: dict) -> np.ndarray:
    """
    Extract 512-dim OSNet appearance embedding from a player crop.
    bbox is {x, y, w, h}.
    Returns a unit-normalized 1D numpy array of shape (512,).
    """
    x, y, w, h = bbox["x"], bbox["y"], bbox["w"], bbox["h"]
    crop = frame[y:y+h, x:x+w]
    if crop.size == 0:
        return np.zeros(512)

    # OSNet expects RGB, resize to 256x128 (standard Re-ID input)
    crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
    crop_resized = cv2.resize(crop_rgb, (128, 256))

    extractor = _get_extractor()
    features = extractor([crop_resized])  # returns (1, 512) tensor
    embedding = features[0].cpu().numpy()

    # L2 normalize
    norm = np.linalg.norm(embedding)
    return embedding / norm if norm > 0 else embedding


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """
    Cosine similarity between two vectors.
    Handles non-unit vectors by normalizing before dot product.
    Returns float in [-1, 1].
    """
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a / norm_a, b / norm_b))


def assign_player_roles(
    seed_embedding: np.ndarray,
    detections: list[dict],
    conf_threshold: float = 0.6,
) -> list[dict]:
    """
    Assign player roles to detections based on similarity to seed_embedding.

    Each detection must have an 'embedding' key (np.ndarray).
    Returns detections with 'role' and 'reid_conf' added.
    Sorted by similarity descending (highest = USER).
    """
    if not detections:
        return []

    scored = []
    for det in detections:
        sim = cosine_similarity(seed_embedding, det["embedding"])
        scored.append({**det, "reid_conf": sim})

    # Sort: highest similarity first = most likely to be the user
    scored.sort(key=lambda d: d["reid_conf"], reverse=True)

    result = []
    for i, det in enumerate(scored):
        role = ROLE_ORDER[i] if i < len(ROLE_ORDER) else None
        result.append({**det, "role": role})

    return result


def court_position_fallback(
    detections: list[dict],
    user_last_x: float,
    frame_width: int,
) -> list[dict]:
    """
    Assign roles by court x-position when Re-ID confidence is low.
    The detection closest to user_last_x gets the USER role.
    """
    if not detections:
        return []

    def center_x(det):
        b = det["bbox"]
        return b["x"] + b["w"] / 2

    centers = [center_x(det) for det in detections]

    # Assign USER to detection closest to last known user position
    closest_idx = min(range(len(centers)), key=lambda i: abs(centers[i] - user_last_x))

    result = []
    role_idx = 0
    for i, det in enumerate(detections):
        if i == closest_idx:
            result.append({**det, "role": PlayerRole.USER, "reid_conf": 0.0, "used_fallback": True})
        else:
            role = ROLE_ORDER[role_idx + 1] if role_idx + 1 < len(ROLE_ORDER) else None
            result.append({**det, "role": role, "reid_conf": 0.0, "used_fallback": True})
            role_idx += 1

    return result


def track_user_across_frames(
    frames: list[np.ndarray],
    all_detections: list[list[dict]],
    seed_embedding: np.ndarray,
    conf_threshold: float = 0.6,
) -> list[list[dict]]:
    """
    Track user across all frames. For each frame, assign roles to detections.
    Falls back to court-position when Re-ID confidence < conf_threshold.

    Returns per-frame list of detections with 'role', 'reid_conf', 'embedding'.
    """
    user_last_x: float = 0.0
    labeled_frames = []

    for frame, frame_detections in zip(frames, all_detections):
        if not frame_detections:
            labeled_frames.append([])
            continue

        enriched = []
        for det in frame_detections:
            emb = extract_embedding(frame, det["bbox"])
            enriched.append({**det, "embedding": emb})

        assigned = assign_player_roles(seed_embedding, enriched, conf_threshold)

        user_det = next((d for d in assigned if d["role"] == PlayerRole.USER), None)
        if user_det and user_det.get("reid_conf", 0) < conf_threshold:
            assigned = court_position_fallback(enriched, user_last_x, frame.shape[1])

        user_det = next((d for d in assigned if d["role"] == PlayerRole.USER), None)
        if user_det:
            b = user_det["bbox"]
            user_last_x = b["x"] + b["w"] / 2

        labeled_frames.append(assigned)

    return labeled_frames
