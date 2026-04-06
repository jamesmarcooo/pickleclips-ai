import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


def _make_mock_conn(fetch_return=None, execute_return=None):
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=fetch_return or [])
    conn.execute = AsyncMock(return_value=execute_return)
    conn.close = AsyncMock()
    return conn


def test_find_stale_jobs_returns_dicts():
    """find_stale_jobs returns a list of dicts for each stale row."""
    mock_row = {"id": "video-123", "r2_key_original": "videos/video-123/original.mp4",
                "r2_key_processed": "videos/video-123/processed.mp4", "user_id": "user-456"}
    mock_conn = _make_mock_conn(fetch_return=[mock_row])

    with patch("asyncpg.connect", AsyncMock(return_value=mock_conn)):
        from app.workers.cleanup import find_stale_jobs
        result = asyncio.run(find_stale_jobs())

    assert result == [mock_row]
    mock_conn.fetch.assert_awaited_once()
    # Query must target stale identifying jobs
    query_arg = mock_conn.fetch.call_args.args[0]
    assert "identifying" in query_arg
    assert "24 hours" in query_arg


def test_cancel_stale_job_sets_timed_out_and_deletes_processed():
    """cancel_stale_job updates status to timed_out and deletes the processed R2 key."""
    mock_conn = _make_mock_conn()

    with patch("asyncpg.connect", AsyncMock(return_value=mock_conn)), \
         patch("app.workers.cleanup.delete_object") as mock_delete:
        from app.workers.cleanup import cancel_stale_job
        asyncio.run(cancel_stale_job(
            "video-123",
            "videos/video-123/original.mp4",
            "videos/video-123/processed.mp4",
        ))

    mock_conn.execute.assert_awaited_once()
    sql_arg = mock_conn.execute.call_args.args[0]
    assert "timed_out" in sql_arg
    mock_delete.assert_called_once_with("videos/video-123/processed.mp4")


def test_cancel_stale_job_skips_delete_when_no_processed_key():
    """cancel_stale_job skips R2 delete when r2_key_processed is None."""
    mock_conn = _make_mock_conn()

    with patch("asyncpg.connect", AsyncMock(return_value=mock_conn)), \
         patch("app.workers.cleanup.delete_object") as mock_delete:
        from app.workers.cleanup import cancel_stale_job
        asyncio.run(cancel_stale_job("video-123", "videos/video-123/original.mp4", None))

    mock_delete.assert_not_called()


def test_cancel_stale_job_swallows_r2_errors():
    """cancel_stale_job does not raise if delete_object raises."""
    mock_conn = _make_mock_conn()

    with patch("asyncpg.connect", AsyncMock(return_value=mock_conn)), \
         patch("app.workers.cleanup.delete_object", side_effect=Exception("R2 down")):
        from app.workers.cleanup import cancel_stale_job
        # Should not raise
        asyncio.run(cancel_stale_job("video-123", "videos/video-123/original.mp4", "key"))


def test_cleanup_stale_jobs_returns_cancelled_count():
    """cleanup_stale_jobs task returns the number of cancelled videos."""
    stale = [
        {"id": "v1", "r2_key_original": "k1", "r2_key_processed": "p1"},
        {"id": "v2", "r2_key_original": "k2", "r2_key_processed": None},
    ]

    with patch("app.workers.cleanup.find_stale_jobs", AsyncMock(return_value=stale)), \
         patch("app.workers.cleanup.cancel_stale_job", AsyncMock()), \
         patch("app.workers.cleanup.schedule_original_deletion", AsyncMock()):
        from app.workers.cleanup import cleanup_stale_jobs
        result = cleanup_stale_jobs()

    assert result == {"cancelled": 2}
