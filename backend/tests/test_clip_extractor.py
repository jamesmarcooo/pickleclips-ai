import pytest
import ffmpeg
from unittest.mock import patch, MagicMock, call
from app.ml.clip_extractor import extract_clip, extract_clips_batch, ClipSpec


def test_extract_clip_calls_ffmpeg_with_correct_args():
    spec = ClipSpec(
        source_path="/tmp/original.mp4",
        output_path="/tmp/clip_001.mp4",
        start_ms=10000,
        end_ms=15000,
    )

    with patch("app.ml.clip_extractor.ffmpeg") as mock_ffmpeg:
        mock_stream = MagicMock()
        mock_ffmpeg.input.return_value = mock_stream
        mock_stream.output.return_value = mock_stream
        mock_stream.overwrite_output.return_value = mock_stream

        extract_clip(spec)

        mock_ffmpeg.input.assert_called_once_with(
            "/tmp/original.mp4",
            ss=10.0,   # start in seconds
            to=15.0,   # end in seconds
        )
        mock_stream.run.assert_called_once()


def test_clip_spec_duration():
    spec = ClipSpec(source_path="a.mp4", output_path="b.mp4", start_ms=5000, end_ms=12000)
    assert spec.duration_seconds == pytest.approx(7.0)


def test_clip_spec_start_seconds():
    spec = ClipSpec(source_path="a.mp4", output_path="b.mp4", start_ms=3500, end_ms=8000)
    assert spec.start_seconds == pytest.approx(3.5)


def test_clip_spec_invalid_range_raises():
    with pytest.raises(ValueError):
        ClipSpec(source_path="a.mp4", output_path="b.mp4", start_ms=5000, end_ms=3000)


def test_extract_clips_batch_skips_failed_clips():
    specs = [
        ClipSpec(source_path="a.mp4", output_path="out1.mp4", start_ms=0, end_ms=5000),
        ClipSpec(source_path="b.mp4", output_path="out2.mp4", start_ms=0, end_ms=5000),
    ]

    err = ffmpeg.Error("ffmpeg", b"", b"fake error")

    def side_effect(spec):
        if spec.source_path == "a.mp4":
            raise err

    with patch("app.ml.clip_extractor.extract_clip", side_effect=side_effect):
        result = extract_clips_batch(specs)

    assert result == ["out2.mp4"]  # only the successful one
