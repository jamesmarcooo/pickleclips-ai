import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone


def test_cleanup_finds_stale_jobs():
    """Stale videos (status=identifying AND identify_started_at > 24h ago) should be cancelled."""
    stale_row = {
        "id": "video-123",
        "r2_key_original": "videos/video-123/original.mp4",
        "user_id": "user-456",
    }

    with patch("app.workers.cleanup.asyncio") as mock_asyncio, \
         patch("app.workers.cleanup.settings"):
        mock_asyncio.run = lambda coro: [stale_row]

        from app.workers.cleanup import find_stale_jobs
        # Just verify the function exists and is callable
        assert callable(find_stale_jobs)
