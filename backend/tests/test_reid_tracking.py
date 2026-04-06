import pytest
import numpy as np
from unittest.mock import patch, MagicMock
from app.ml.reid_tracking import (
    extract_embedding,
    cosine_similarity,
    assign_player_roles,
    court_position_fallback,
    PlayerRole,
)


def test_cosine_similarity_identical_vectors():
    v = np.array([1.0, 0.0, 0.5])
    assert cosine_similarity(v, v) == pytest.approx(1.0, abs=1e-6)


def test_cosine_similarity_orthogonal_vectors():
    v1 = np.array([1.0, 0.0])
    v2 = np.array([0.0, 1.0])
    assert cosine_similarity(v1, v2) == pytest.approx(0.0, abs=1e-6)


def test_assign_player_roles_high_confidence():
    """Highest-similarity detection gets role 'user'."""
    seed_embedding = np.array([1.0, 0.0, 0.0])
    detections = [
        {"bbox": {"x": 100, "y": 200, "w": 80, "h": 180}, "embedding": np.array([0.9, 0.1, 0.0])},
        {"bbox": {"x": 500, "y": 200, "w": 80, "h": 180}, "embedding": np.array([0.1, 0.9, 0.0])},
    ]
    roles = assign_player_roles(seed_embedding, detections, conf_threshold=0.5)
    assert roles[0]["role"] == PlayerRole.USER
    assert roles[1]["role"] != PlayerRole.USER


def test_court_position_fallback_assigns_by_x_position():
    """When Re-ID fails, fallback assigns roles by court x-position."""
    detections = [
        {"bbox": {"x": 100, "y": 300, "w": 80, "h": 180}},   # left side
        {"bbox": {"x": 900, "y": 300, "w": 80, "h": 180}},   # right side
    ]
    result = court_position_fallback(
        detections=detections,
        user_last_x=150,
        frame_width=1920,
    )
    assert result[0]["role"] == PlayerRole.USER
