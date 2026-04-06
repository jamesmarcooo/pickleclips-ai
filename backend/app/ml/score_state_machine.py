from enum import Enum
from dataclasses import dataclass, field
from typing import Literal


class PointOutcome(str, Enum):
    USER_TEAM_WINS = "user_team"
    OPPONENT_TEAM_WINS = "opponent_team"


@dataclass
class ScoreStateMachine:
    """
    Tracks pickleball score state using the rally-end signals from the rally detector.

    Pickleball rules:
    - Only serving team can score
    - Non-serving team winning a rally = side out (serve changes, no score)
    - In doubles: each team has 2 serves per rotation (first server exception at start)
    - First to 11, win by 2
    """
    serving_team: Literal["user_team", "opponent_team"] = "user_team"
    user_team_score: int = 0
    opponent_team_score: int = 0
    server_number: int = 1  # 1 or 2 in doubles
    is_first_serve: bool = True  # First server exception
    history: list[dict] = field(default_factory=list)

    def get_state(self) -> dict:
        return {
            "user_team": self.user_team_score,
            "opponent_team": self.opponent_team_score,
            "serving_team": self.serving_team,
            "server_number": self.server_number,
        }

    def record_point(self, outcome: PointOutcome) -> dict:
        """
        Record the outcome of a rally and update state.
        Returns a dict with score_before, score_after, and point_won_by.
        """
        if self.is_game_over:
            raise ValueError("Cannot record a point after the game has ended.")
        score_before = self.get_state()

        if outcome.value == self.serving_team:
            # Serving team wins the rally → score
            if self.serving_team == "user_team":
                self.user_team_score += 1
            else:
                self.opponent_team_score += 1
        else:
            # Non-serving team wins → side out
            if self.is_first_serve:
                # First server exception: immediately switch serving team
                self.is_first_serve = False
                self.serving_team = outcome.value
                self.server_number = 1
            elif self.server_number == 1:
                # Switch to second server on same team
                self.server_number = 2
            else:
                # Both servers used → switch serving team
                self.serving_team = outcome.value
                self.server_number = 1

        score_after = self.get_state().copy()
        record = {
            "score_before": score_before,
            "score_after": score_after,
            "point_won_by": outcome.value,
            "serving_team_at_start": score_before["serving_team"],
        }
        self.history.append(record)
        return record

    @property
    def is_game_over(self) -> bool:
        max_score = max(self.user_team_score, self.opponent_team_score)
        min_score = min(self.user_team_score, self.opponent_team_score)
        return max_score >= 11 and (max_score - min_score) >= 2
