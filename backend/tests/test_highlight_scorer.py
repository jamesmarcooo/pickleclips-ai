import pytest
from app.ml.highlight_scorer import score_highlight, RoleWeights


def test_user_scoring_point_gets_highest_score():
    score = score_highlight(
        point_scored=True,
        point_won_by="user_team",
        rally_length=5,
        attributed_role="user",
    )
    assert score > 0.5


def test_opponent_scoring_gets_low_score():
    score = score_highlight(
        point_scored=True,
        point_won_by="opponent_team",
        rally_length=5,
        attributed_role="opponent_1",
    )
    assert score < 0.3


def test_long_rally_scores_higher_than_short():
    short = score_highlight(point_scored=False, point_won_by=None, rally_length=3, attributed_role="user")
    long = score_highlight(point_scored=False, point_won_by=None, rally_length=15, attributed_role="user")
    assert long > short


def test_partner_play_lower_than_user():
    user_score = score_highlight(point_scored=True, point_won_by="user_team", rally_length=5, attributed_role="user")
    partner_score = score_highlight(point_scored=True, point_won_by="user_team", rally_length=5, attributed_role="partner")
    assert user_score > partner_score


def test_lowlight_detection_weak_shot():
    is_lowlight = score_highlight(
        point_scored=False,
        point_won_by=None,
        rally_length=2,
        attributed_role="user",
        shot_quality=0.15,
    )
    # A shot_quality < 0.3 should flag as potential lowlight
    assert is_lowlight < 0.2
