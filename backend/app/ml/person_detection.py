from typing import TypedDict
import numpy as np
from ultralytics import YOLO

# Module-level model (loaded once per worker process)
_model: YOLO | None = None


class BoundingBox(TypedDict):
    x: int  # top-left x
    y: int  # top-left y
    w: int  # width
    h: int  # height


def _get_model() -> YOLO:
    global _model
    if _model is None:
        _model = YOLO("yolov8n.pt")  # downloads ~6MB on first run
    return _model


def detect_players(frame: np.ndarray, max_players: int = 4) -> list[BoundingBox]:
    """
    Detect people in a frame using YOLOv8n.
    Returns up to max_players bounding boxes sorted by confidence (descending).
    Each bbox is {x, y, w, h} in pixels (top-left origin, positive dimensions).
    """
    model = _get_model()
    results = model(frame, classes=[0], verbose=False)  # class 0 = person

    bboxes: list[tuple[float, BoundingBox]] = []  # (confidence, bbox)

    for result in results:
        boxes = result.boxes
        if boxes is None or len(boxes.xyxy) == 0:
            continue

        for i in range(len(boxes.xyxy)):
            conf = float(boxes.conf[i])
            x1, y1, x2, y2 = [float(v) for v in boxes.xyxy[i]]
            bbox: BoundingBox = {
                "x": int(x1),
                "y": int(y1),
                "w": int(x2 - x1),
                "h": int(y2 - y1),
            }
            bboxes.append((conf, bbox))

    # Sort by confidence descending, take top max_players
    bboxes.sort(key=lambda t: t[0], reverse=True)
    return [bbox for _, bbox in bboxes[:max_players]]
