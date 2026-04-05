import pytest
from unittest.mock import patch, MagicMock
from app.services.storage import generate_upload_url, generate_download_url, delete_object


def test_generate_upload_url_returns_string():
    with patch("app.services.storage.get_r2_client") as mock_client:
        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.return_value = "https://r2.example.com/upload?sig=abc"
        mock_client.return_value = mock_s3

        url = generate_upload_url("videos/test-id/original.mp4")

        assert url.startswith("https://")
        mock_s3.generate_presigned_url.assert_called_once_with(
            "put_object",
            Params={
                "Bucket": mock_s3.generate_presigned_url.call_args.kwargs["Params"]["Bucket"],
                "Key": "videos/test-id/original.mp4",
                "ContentType": "video/mp4",
            },
            ExpiresIn=3600,
        )


def test_generate_download_url_returns_string():
    with patch("app.services.storage.get_r2_client") as mock_client:
        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.return_value = "https://r2.example.com/download?sig=xyz"
        mock_client.return_value = mock_s3

        url = generate_download_url("clips/test-id/clip-001.mp4")
        assert url.startswith("https://")


def test_delete_object_calls_delete():
    with patch("app.services.storage.get_r2_client") as mock_client:
        mock_s3 = MagicMock()
        mock_client.return_value = mock_s3

        delete_object("videos/test-id/original.mp4")

        mock_s3.delete_object.assert_called_once()
