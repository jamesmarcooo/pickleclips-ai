import pytest
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError
from app.services.storage import (
    generate_upload_url,
    generate_download_url,
    delete_object,
    generate_multipart_upload_id,
    sign_multipart_part,
    complete_multipart_upload,
    abort_multipart_upload,
    StorageError,
)

TEST_BUCKET = "test-bucket"
TEST_KEY = "videos/test-id/original.mp4"


def _make_client_error():
    return ClientError({"Error": {"Code": "NoSuchKey", "Message": "Not found"}}, "GetObject")


def test_generate_upload_url_returns_string():
    with patch("app.services.storage.get_r2_client") as mock_get_client:
        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.return_value = "https://r2.example.com/upload?sig=abc"
        mock_get_client.return_value = mock_s3

        url = generate_upload_url(TEST_KEY)

        assert url.startswith("https://")
        call_kwargs = mock_s3.generate_presigned_url.call_args
        assert call_kwargs.args[0] == "put_object"
        assert call_kwargs.kwargs["Params"]["Key"] == TEST_KEY
        assert call_kwargs.kwargs["Params"]["ContentType"] == "video/mp4"
        assert call_kwargs.kwargs["ExpiresIn"] == 3600


def test_generate_upload_url_raises_storage_error_on_failure():
    with patch("app.services.storage.get_r2_client") as mock_get_client:
        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.side_effect = _make_client_error()
        mock_get_client.return_value = mock_s3

        with pytest.raises(StorageError):
            generate_upload_url(TEST_KEY)


def test_generate_download_url_returns_string():
    with patch("app.services.storage.get_r2_client") as mock_get_client:
        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.return_value = "https://r2.example.com/download?sig=xyz"
        mock_get_client.return_value = mock_s3

        url = generate_download_url("clips/test-id/clip-001.mp4")
        assert url.startswith("https://")


def test_delete_object_calls_delete():
    with patch("app.services.storage.get_r2_client") as mock_get_client:
        mock_s3 = MagicMock()
        mock_get_client.return_value = mock_s3

        delete_object(TEST_KEY)

        mock_s3.delete_object.assert_called_once()


def test_generate_multipart_upload_id():
    with patch("app.services.storage.get_r2_client") as mock_get_client:
        mock_s3 = MagicMock()
        mock_s3.create_multipart_upload.return_value = {"UploadId": "upload-123"}
        mock_get_client.return_value = mock_s3

        upload_id = generate_multipart_upload_id(TEST_KEY)

        assert upload_id == "upload-123"
        mock_s3.create_multipart_upload.assert_called_once()


def test_sign_multipart_part():
    with patch("app.services.storage.get_r2_client") as mock_get_client:
        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.return_value = "https://r2.example.com/part?sig=p1"
        mock_get_client.return_value = mock_s3

        url = sign_multipart_part(TEST_KEY, "upload-123", 1)

        assert url.startswith("https://")
        call_kwargs = mock_s3.generate_presigned_url.call_args
        assert call_kwargs.args[0] == "upload_part"
        assert call_kwargs.kwargs["Params"]["PartNumber"] == 1
        assert call_kwargs.kwargs["Params"]["UploadId"] == "upload-123"


def test_complete_multipart_upload():
    with patch("app.services.storage.get_r2_client") as mock_get_client:
        mock_s3 = MagicMock()
        mock_get_client.return_value = mock_s3

        parts = [{"ETag": '"abc123"', "PartNumber": 1}]
        complete_multipart_upload(TEST_KEY, "upload-123", parts)

        mock_s3.complete_multipart_upload.assert_called_once()
        call_kwargs = mock_s3.complete_multipart_upload.call_args.kwargs
        assert call_kwargs["MultipartUpload"] == {"Parts": parts}


def test_abort_multipart_upload():
    with patch("app.services.storage.get_r2_client") as mock_get_client:
        mock_s3 = MagicMock()
        mock_get_client.return_value = mock_s3

        abort_multipart_upload(TEST_KEY, "upload-123")

        mock_s3.abort_multipart_upload.assert_called_once()
