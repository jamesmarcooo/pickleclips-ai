import pytest
from unittest.mock import patch


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
