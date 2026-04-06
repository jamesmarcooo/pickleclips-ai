import pytest
import numpy as np
from unittest.mock import patch, MagicMock
from app.ml.person_detection import detect_players, BoundingBox


def make_mock_result(boxes_xyxy: list[list[float]]):
    """Create a mock YOLO result with given bounding boxes."""
    mock_result = MagicMock()
    mock_boxes = MagicMock()

    import torch
    mock_boxes.xyxy = torch.tensor(boxes_xyxy, dtype=torch.float32)
    mock_boxes.cls = torch.zeros(len(boxes_xyxy))  # all class 0 = person
    mock_boxes.conf = torch.ones(len(boxes_xyxy)) * 0.9
    mock_result.boxes = mock_boxes

    return [mock_result]


def test_detect_players_returns_up_to_4_people():
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)

    # Mock YOLO returning 5 detections (should clamp to 4 most confident)
    boxes = [[100, 200, 200, 500], [300, 200, 400, 500],
             [600, 200, 700, 500], [900, 200, 1000, 500],
             [1100, 200, 1200, 500]]  # 5 boxes

    with patch("app.ml.person_detection.YOLO") as MockYOLO, \
         patch("app.ml.person_detection._model", None):
        mock_model = MagicMock()
        mock_model.return_value = make_mock_result(boxes)
        MockYOLO.return_value = mock_model

        result = detect_players(frame)

    assert len(result) <= 4
    assert all(isinstance(b, dict) for b in result)
    assert all({"x", "y", "w", "h"}.issubset(b.keys()) for b in result)


def test_detect_players_converts_xyxy_to_xywh():
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    boxes = [[100.0, 200.0, 300.0, 600.0]]  # x1=100, y1=200, x2=300, y2=600

    with patch("app.ml.person_detection.YOLO") as MockYOLO, \
         patch("app.ml.person_detection._model", None):
        mock_model = MagicMock()
        mock_model.return_value = make_mock_result(boxes)
        MockYOLO.return_value = mock_model

        result = detect_players(frame)

    assert len(result) == 1
    b = result[0]
    assert b["x"] == 100
    assert b["y"] == 200
    assert b["w"] == 200   # x2 - x1
    assert b["h"] == 400   # y2 - y1


def test_detect_players_returns_empty_if_no_people():
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)

    with patch("app.ml.person_detection.YOLO") as MockYOLO, \
         patch("app.ml.person_detection._model", None):
        mock_model = MagicMock()
        mock_model.return_value = make_mock_result([])
        MockYOLO.return_value = mock_model

        result = detect_players(frame)

    assert result == []
