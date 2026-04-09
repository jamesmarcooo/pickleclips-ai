import pytest
import numpy as np
from unittest.mock import AsyncMock, patch


def test_upsert_creates_new_profile(mock_db_connection):
    # 10 labeled frames each with a user embedding
    embedding = np.random.randn(512).astype(np.float32)
    embedding /= np.linalg.norm(embedding)
    labeled_frames = [[{"role": "user", "embedding": embedding, "reid_conf": 0.9}]] * 10

    with patch("app.workers.ingest.asyncpg.connect") as mock_connect:
        mock_conn = AsyncMock()
        mock_connect.return_value = mock_conn
        from app.workers.ingest import _upsert_player_profile
        _upsert_player_profile("vid-001", "user-001", labeled_frames)

    mock_conn.execute.assert_called_once()
    call_args = mock_conn.execute.call_args[0]
    assert "INSERT INTO player_profiles" in call_args[0]
    assert call_args[3] == pytest.approx(0.9, abs=0.01)  # avg_confidence ($3 positional arg)


def test_upsert_skipped_when_no_user_embeddings(mock_db_connection):
    labeled_frames = [[{"role": "partner", "embedding": np.zeros(512)}]] * 5

    with patch("app.workers.ingest.asyncpg.connect") as mock_connect:
        from app.workers.ingest import _upsert_player_profile
        _upsert_player_profile("vid-002", "user-002", labeled_frames)

    mock_connect.assert_not_called()  # early return, no DB hit
