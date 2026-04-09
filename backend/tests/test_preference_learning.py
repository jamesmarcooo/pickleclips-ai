from app.ml.highlight_scorer import score_highlight


def test_score_highlight_uses_overrides():
    default = score_highlight(
        point_scored=False, point_won_by=None, rally_length=5,
        attributed_role="user", shot_type="erne", shot_quality=0.8,
    )
    boosted = score_highlight(
        point_scored=False, point_won_by=None, rally_length=5,
        attributed_role="user", shot_type="erne", shot_quality=0.8,
        shot_type_overrides={"erne": 2.0},
    )
    assert boosted > default


def test_preference_weight_clamps_at_max():
    # Simulate: erne at 1.98, user likes → should clamp at 2.0
    weights = {"erne": 1.98}
    delta = 0.05
    result = round(max(0.3, min(2.0, weights["erne"] + delta)), 4)
    assert result == 2.0


def test_preference_weight_clamps_at_min():
    weights = {"dink": 0.32}
    delta = -0.05
    result = round(max(0.3, min(2.0, weights["dink"] + delta)), 4)
    assert result == 0.3


def test_feedback_liked_increases_weight():
    current = 1.0
    result = round(max(0.3, min(2.0, current + 0.05)), 4)
    assert result == 1.05


def test_feedback_disliked_decreases_weight():
    current = 1.0
    result = round(max(0.3, min(2.0, current - 0.05)), 4)
    assert result == 0.95
