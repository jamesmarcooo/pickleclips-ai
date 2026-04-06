import pytest
from app.ml.score_state_machine import ScoreStateMachine, PointOutcome


def test_initial_state():
    sm = ScoreStateMachine()
    state = sm.get_state()
    assert state["user_team"] == 0
    assert state["opponent_team"] == 0
    assert state["serving_team"] in ("user_team", "opponent_team")


def test_serving_team_scores_increments_score():
    sm = ScoreStateMachine(serving_team="user_team")
    sm.record_point(PointOutcome.USER_TEAM_WINS)
    state = sm.get_state()
    assert state["user_team"] == 1
    assert state["opponent_team"] == 0


def test_non_serving_team_wins_causes_side_out():
    sm = ScoreStateMachine(serving_team="user_team")
    sm.record_point(PointOutcome.OPPONENT_TEAM_WINS)
    state = sm.get_state()
    # Side out: serving switches, score unchanged
    assert state["user_team"] == 0
    assert state["serving_team"] == "opponent_team"


def test_history_records_all_points():
    sm = ScoreStateMachine()
    sm.record_point(PointOutcome.USER_TEAM_WINS)
    sm.record_point(PointOutcome.OPPONENT_TEAM_WINS)
    assert len(sm.history) == 2


def test_point_outcome_includes_before_and_after():
    sm = ScoreStateMachine(serving_team="user_team")
    before = sm.get_state().copy()
    outcome = sm.record_point(PointOutcome.USER_TEAM_WINS)
    assert outcome["score_before"] == before
    assert outcome["score_after"]["user_team"] == 1
