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
    sm = ScoreStateMachine(serving_team="user_team", is_first_serve=False)
    sm.record_point(PointOutcome.OPPONENT_TEAM_WINS)
    state = sm.get_state()
    # server_number goes 1→2, serving_team stays "user_team"
    assert state["user_team"] == 0
    assert state["server_number"] == 2
    assert state["serving_team"] == "user_team"


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


def test_second_server_side_out_switches_serving_team():
    """After both servers fail, serve passes to the other team."""
    sm = ScoreStateMachine(serving_team="user_team", is_first_serve=False, server_number=2)
    sm.record_point(PointOutcome.OPPONENT_TEAM_WINS)
    state = sm.get_state()
    assert state["serving_team"] == "opponent_team"
    assert state["server_number"] == 1


def test_is_game_over_at_11_win_by_2():
    sm = ScoreStateMachine(serving_team="user_team", is_first_serve=False)
    # Score user_team to 11
    for _ in range(11):
        sm.record_point(PointOutcome.USER_TEAM_WINS)
    assert sm.is_game_over is True
    # 11-0 is over (win by more than 2 is fine)
    assert sm.user_team_score == 11
    assert sm.opponent_team_score == 0
