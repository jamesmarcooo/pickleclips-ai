import pytest
from app.services.reel import select_clips_for_output_type


def _make_highlight(id: str, score: float, shot_type: str = "drive",
                    sub_type: str = "point_scored", role: str = "user"):
    return {
        "id": id,
        "highlight_score": score,
        "shot_type": shot_type,
        "sub_highlight_type": sub_type,
        "attributed_player_role": role,
        "r2_key_clip": f"clips/{id}.mp4",
    }


def test_highlight_montage_returns_top_10():
    highlights = [_make_highlight(str(i), float(i) / 10) for i in range(20)]
    selected = select_clips_for_output_type("highlight_montage", highlights, lowlights=[])
    assert len(selected) <= 10
    scores = [h["highlight_score"] for h in selected]
    assert scores == sorted(scores, reverse=True)


def test_my_best_plays_filters_to_user_only():
    highlights = [
        _make_highlight("1", 0.9, role="user"),
        _make_highlight("2", 0.8, role="partner"),
        _make_highlight("3", 0.7, role="opponent_1"),
    ]
    selected = select_clips_for_output_type("my_best_plays", highlights, lowlights=[])
    assert all(h["attributed_player_role"] == "user" for h in selected)


def test_points_of_improvement_uses_lowlights():
    highlights = [_make_highlight("1", 0.9)]
    lowlights = [
        {"id": "l1", "shot_quality": 0.1, "r2_key_clip": "clips/l1.mp4", "sub_highlight_type": "lowlight"},
        {"id": "l2", "shot_quality": 0.2, "r2_key_clip": "clips/l2.mp4", "sub_highlight_type": "lowlight"},
    ]
    selected = select_clips_for_output_type("points_of_improvement", highlights, lowlights=lowlights)
    assert all(h["sub_highlight_type"] == "lowlight" for h in selected)


def test_game_recap_includes_all_scored_points():
    highlights = [
        _make_highlight("1", 0.9, sub_type="point_scored"),
        _make_highlight("2", 0.6, sub_type="shot_form"),
        _make_highlight("3", 0.7, sub_type="point_scored"),
    ]
    selected = select_clips_for_output_type("game_recap", highlights, lowlights=[])
    ids = {h["id"] for h in selected}
    assert "1" in ids and "3" in ids
    assert "2" not in ids
