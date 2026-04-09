from dataclasses import dataclass
from typing import Literal


@dataclass
class RoleWeights:
    user: float = 1.0
    partner: float = 0.7
    opponent_1: float = 0.3
    opponent_2: float = 0.3


_SHOT_TYPE_MULTIPLIERS: dict[str, float] = {
    "erne": 1.3,
    "atp": 1.3,
    "smash": 1.3,
    "overhead": 1.1,
    "lob": 1.05,
    "drive": 1.0,
    "speed_up": 1.0,
    "dink": 0.9,
    "drop": 0.9,
}


def score_highlight(
    point_scored: bool,
    point_won_by: Literal["user_team", "opponent_team"] | None,
    rally_length: int,
    attributed_role: str,
    shot_quality: float = 0.5,
    shot_type: str | None = None,
    weights: RoleWeights | None = None,
    shot_type_overrides: dict[str, float] | None = None,
) -> float:
    """
    Phase 1 highlight scorer. Uses only signals available without ball/pose models.
    Returns a score in [0, 1].

    Signals:
    - point_scored + point_won_by: strongest highlight trigger
    - rally_length: longer rallies are more exciting
    - attributed_role: user's plays ranked above partner/opponents
    - shot_quality: 0-1 float (defaults to 0.5 when shot classifier not available)
    """
    if weights is None:
        weights = RoleWeights()

    # Base score from rally excitement (normalized, plateau at 20 shots)
    rally_score = min(rally_length / 20.0, 1.0) * 0.3

    # Shot quality contribution
    quality_score = shot_quality * 0.2

    # Point outcome
    point_score = 0.0
    if point_scored and point_won_by == "user_team":
        point_score = 0.5
    elif point_scored and point_won_by == "opponent_team":
        point_score = 0.05  # opponent scoring is low interest

    raw_score = rally_score + quality_score + point_score

    # Role-aware weighting
    if attributed_role == "user":
        role_weight = weights.user
    elif attributed_role == "partner":
        role_weight = weights.partner
    elif attributed_role in ("opponent_1", "opponent_2"):
        role_weight = weights.opponent_1
    else:
        raise ValueError(f"Unknown attributed_role: {attributed_role!r}. Expected one of: user, partner, opponent_1, opponent_2")

    final_score = raw_score * role_weight
    multipliers = dict(_SHOT_TYPE_MULTIPLIERS)
    if shot_type_overrides:
        multipliers.update(shot_type_overrides)
    shot_multiplier = multipliers.get(shot_type or "", 1.0)
    final_score = final_score * shot_multiplier
    return min(final_score, 1.0)


def is_lowlight(shot_quality: float, point_lost_by_error: bool) -> bool:
    """
    Phase 1 lowlight detection: weak shot quality OR lost point by user error.
    """
    return shot_quality < 0.3 or point_lost_by_error


def rank_highlights(highlights: list[dict]) -> list[dict]:
    """Sort highlights by highlight_score descending."""
    return sorted(highlights, key=lambda h: h.get("highlight_score", 0), reverse=True)
