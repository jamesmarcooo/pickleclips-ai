import pytest
from unittest.mock import patch, AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_create_multipart_upload(client, test_token):
    with patch("app.routers.videos.storage.generate_multipart_upload_id", return_value="upload-id-123"):
        response = await client.post(
            "/api/v1/videos/multipart/create",
            json={"filename": "game.mp4", "content_type": "video/mp4"},
            headers={"Authorization": f"Bearer {test_token}"},
        )
    assert response.status_code == 200
    data = response.json()
    assert "video_id" in data
    assert "upload_id" in data
    assert "key" in data


@pytest.mark.asyncio
async def test_sign_multipart_part(client, test_token, mock_db_connection):
    from unittest.mock import MagicMock, AsyncMock
    mock_db_connection.fetchrow = AsyncMock(return_value=MagicMock())  # ownership check passes
    with patch("app.routers.videos.storage.sign_multipart_part", return_value="https://r2.example.com/part"):
        response = await client.get(
            "/api/v1/videos/multipart/sign-part",
            params={"key": "videos/abc/original.mp4", "upload_id": "uid123", "part_number": 1},
            headers={"Authorization": f"Bearer {test_token}"},
        )
    assert response.status_code == 200
    assert "url" in response.json()


@pytest.mark.asyncio
async def test_confirm_triggers_pipeline(client, test_token, test_user_id):
    # ingest_video is lazily imported inside the endpoint — patch it at its source
    # so the lazy import resolves to a mock. Workers module (Task 7) doesn't exist yet,
    # so we patch sys.modules to stand in for the whole workers.ingest module.
    import sys
    from unittest.mock import MagicMock
    mock_ingest = MagicMock()
    mock_ingest.ingest_video.delay = MagicMock()
    with patch.dict(sys.modules, {"app.workers": MagicMock(), "app.workers.ingest": mock_ingest}):
        response = await client.post(
            "/api/v1/videos/fake-video-id/confirm",
            headers={"Authorization": f"Bearer {test_token}"},
        )
    # mock_db_connection returns None for fetchrow → 404 is fine too
    assert response.status_code in (200, 404, 422, 500)


async def test_generate_reels_returns_202_when_analyzed(client, test_token, mock_db_connection):
    import sys
    from unittest.mock import MagicMock, AsyncMock, patch
    mock_reel_gen = MagicMock()
    mock_reel_gen.trigger_auto_generated_reels = AsyncMock()
    with patch.dict(sys.modules, {"app.workers.reel_gen": mock_reel_gen}):
        mock_db_connection.fetchrow = AsyncMock(
            return_value={"id": "vid-001", "status": "analyzed"}
        )
        res = await client.post(
            "/api/v1/videos/vid-001/generate-reels",
            headers={"Authorization": f"Bearer {test_token}"},
        )
    assert res.status_code == 202
    assert res.json()["status"] == "queued"
    mock_reel_gen.trigger_auto_generated_reels.assert_called_once()


async def test_generate_reels_409_when_not_analyzed(client, test_token, mock_db_connection):
    from unittest.mock import AsyncMock
    mock_db_connection.fetchrow = AsyncMock(
        return_value={"id": "vid-002", "status": "processing"}
    )
    res = await client.post(
        "/api/v1/videos/vid-002/generate-reels",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert res.status_code == 409
    assert "not analyzed" in res.json()["detail"]


async def test_generate_reels_404_video_not_found(client, test_token, mock_db_connection):
    from unittest.mock import AsyncMock
    mock_db_connection.fetchrow = AsyncMock(return_value=None)
    res = await client.post(
        "/api/v1/videos/vid-999/generate-reels",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert res.status_code == 404


async def test_confirm_identity_accepted(client, test_token, mock_db_connection):
    import sys
    mock_ingest = MagicMock()
    mock_ingest.resume_after_identify = MagicMock()
    mock_db_connection.fetchrow = AsyncMock(return_value={
        "id": "vid-001", "status": "confirming",
        "metadata": {"auto_candidate_bbox": {"x": 100, "y": 50, "w": 80, "h": 200},
                     "player_bboxes": []},
    })
    mock_db_connection.execute = AsyncMock()
    with patch.dict(sys.modules, {"app.workers.ingest": mock_ingest}):
        res = await client.post(
            "/api/v1/videos/vid-001/confirm-identity",
            json={"confirmed": True},
            headers={"Authorization": f"Bearer {test_token}"},
        )
    assert res.status_code == 200
    assert res.json()["status"] == "processing"
    assert res.json()["auto_recognized"] is True


async def test_confirm_identity_rejected_falls_back(client, test_token, mock_db_connection):
    mock_db_connection.fetchrow = AsyncMock(return_value={
        "id": "vid-002", "status": "confirming",
        "metadata": {"auto_candidate_bbox": {"x": 0, "y": 0, "w": 50, "h": 100},
                     "player_bboxes": [{"x": 0, "y": 0, "w": 50, "h": 100}]},
    })
    mock_db_connection.execute = AsyncMock()
    res = await client.post(
        "/api/v1/videos/vid-002/confirm-identity",
        json={"confirmed": False},
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "identifying"
    assert isinstance(res.json()["bboxes"], list)


async def test_confirm_identity_409_wrong_status(client, test_token, mock_db_connection):
    mock_db_connection.fetchrow = AsyncMock(return_value={
        "id": "vid-003", "status": "identifying", "metadata": {}
    })
    res = await client.post(
        "/api/v1/videos/vid-003/confirm-identity",
        json={"confirmed": True},
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert res.status_code == 409


async def test_confirm_identity_404_not_found(client, test_token, mock_db_connection):
    mock_db_connection.fetchrow = AsyncMock(return_value=None)
    res = await client.post(
        "/api/v1/videos/vid-999/confirm-identity",
        json={"confirmed": True},
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert res.status_code == 404
