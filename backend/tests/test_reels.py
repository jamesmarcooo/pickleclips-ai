import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import uuid


@pytest.mark.asyncio
async def test_list_reels_for_video(client, test_token, mock_db_connection):
    video_id = str(uuid.uuid4())
    mock_db_connection.fetchrow = AsyncMock(return_value=MagicMock())  # video ownership passes
    mock_db_connection.fetch = AsyncMock(return_value=[])
    resp = await client.get(
        f"/api/v1/videos/{video_id}/reels",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_create_reel_queues_task(client, test_token, mock_db_connection):
    video_id = str(uuid.uuid4())
    reel_id = str(uuid.uuid4())
    mock_db_connection.fetchrow = AsyncMock(side_effect=[
        MagicMock(spec=["__getitem__"]),  # analyzed video found
        {"id": reel_id, "status": "queued"},  # INSERT RETURNING
    ])

    import sys
    mock_reel_gen = MagicMock()
    mock_reel_gen.generate_reel.delay = MagicMock()
    with patch.dict(sys.modules, {"app.workers.reel_gen": mock_reel_gen}):
        resp = await client.post(
            "/api/v1/reels",
            json={"video_id": video_id, "output_type": "highlight_montage", "format": "horizontal"},
            headers={"Authorization": f"Bearer {test_token}"},
        )
    assert resp.status_code == 201
    data = resp.json()
    assert "id" in data
    assert data["status"] == "queued"


@pytest.mark.asyncio
async def test_get_reel_not_found_returns_404(client, test_token, mock_db_connection):
    mock_db_connection.fetchrow = AsyncMock(return_value=None)
    reel_id = str(uuid.uuid4())
    resp = await client.get(
        f"/api/v1/reels/{reel_id}",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_share_reel_returns_share_url(client, test_token, mock_db_connection):
    reel_id = str(uuid.uuid4())
    mock_row = {
        "id": reel_id,
        "status": "ready",
        "share_token": "existing-token",
        "r2_key": "reels/test/output.mp4",
    }
    mock_db_connection.fetchrow = AsyncMock(return_value=mock_row)
    resp = await client.post(
        f"/api/v1/reels/{reel_id}/share",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "share_url" in data
    assert data["share_url"].startswith("http")


@pytest.mark.asyncio
async def test_public_share_page_no_auth_required(client, mock_db_connection):
    mock_row = {
        "id": str(uuid.uuid4()),
        "output_type": "highlight_montage",
        "format": "horizontal",
        "duration_seconds": 30.0,
        "r2_key": "reels/test/output.mp4",
    }
    mock_db_connection.fetchrow = AsyncMock(return_value=mock_row)
    with patch("app.routers.reels.generate_download_url", return_value="https://r2.example.com/reel.mp4"):
        resp = await client.get("/api/v1/reels/share/some-share-token")
    assert resp.status_code == 200
    data = resp.json()
    assert "output_type" in data
    assert "download_url" in data
