import io
import zipfile
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

TEST_VIDEO_ID = "00000000-0000-0000-0000-000000000099"
TEST_HIGHLIGHT_ID = "aaaaaaaa-0000-0000-0000-000000000001"

pytestmark = pytest.mark.asyncio


async def test_download_zip_returns_200_with_clips(client, test_token, mock_db_connection):
    mock_db_connection.fetchrow = AsyncMock(return_value={"id": TEST_VIDEO_ID})
    mock_db_connection.fetch = AsyncMock(return_value=[
        {"id": TEST_HIGHLIGHT_ID, "shot_type": "erne", "r2_key_clip": "videos/x/clips/a.mp4"},
    ])
    mock_r2 = MagicMock()
    mock_r2.get_object.return_value = {"Body": io.BytesIO(b"fakevideo")}
    with patch("app.routers.highlights.get_r2_client", return_value=mock_r2):
        res = await client.get(
            f"/api/v1/videos/{TEST_VIDEO_ID}/clips/download-zip",
            headers={"Authorization": f"Bearer {test_token}"},
        )
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/zip"
    assert "clips_" in res.headers["content-disposition"]
    buf = io.BytesIO(res.content)
    with zipfile.ZipFile(buf) as zf:
        assert f"erne/{TEST_HIGHLIGHT_ID}.mp4" in zf.namelist()


async def test_download_zip_404_video_not_found(client, test_token, mock_db_connection):
    mock_db_connection.fetchrow = AsyncMock(return_value=None)
    res = await client.get(
        f"/api/v1/videos/{TEST_VIDEO_ID}/clips/download-zip",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert res.status_code == 404


async def test_download_zip_409_no_clips_yet(client, test_token, mock_db_connection):
    mock_db_connection.fetchrow = AsyncMock(return_value={"id": TEST_VIDEO_ID})
    mock_db_connection.fetch = AsyncMock(return_value=[])
    res = await client.get(
        f"/api/v1/videos/{TEST_VIDEO_ID}/clips/download-zip",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert res.status_code == 409
    assert "No clips" in res.json()["detail"]


async def test_download_zip_skips_failed_r2_fetch(client, test_token, mock_db_connection):
    mock_db_connection.fetchrow = AsyncMock(return_value={"id": TEST_VIDEO_ID})
    mock_db_connection.fetch = AsyncMock(return_value=[
        {"id": "aaaa0001-0000-0000-0000-000000000001", "shot_type": "drive", "r2_key_clip": "k1"},
        {"id": "aaaa0002-0000-0000-0000-000000000002", "shot_type": "dink",  "r2_key_clip": "k2"},
    ])
    mock_r2 = MagicMock()
    mock_r2.get_object.side_effect = [Exception("R2 error"), {"Body": io.BytesIO(b"ok")}]
    with patch("app.routers.highlights.get_r2_client", return_value=mock_r2):
        res = await client.get(
            f"/api/v1/videos/{TEST_VIDEO_ID}/clips/download-zip",
            headers={"Authorization": f"Bearer {test_token}"},
        )
    assert res.status_code == 200
    buf = io.BytesIO(res.content)
    with zipfile.ZipFile(buf) as zf:
        names = zf.namelist()
    assert len(names) == 1
    assert "dink/" in names[0]
