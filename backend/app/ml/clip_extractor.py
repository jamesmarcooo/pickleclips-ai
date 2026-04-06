import logging
from dataclasses import dataclass

import ffmpeg

logger = logging.getLogger(__name__)


@dataclass
class ClipSpec:
    source_path: str
    output_path: str
    start_ms: int
    end_ms: int

    def __post_init__(self):
        if self.end_ms <= self.start_ms:
            raise ValueError(f"end_ms ({self.end_ms}) must be greater than start_ms ({self.start_ms})")

    @property
    def start_seconds(self) -> float:
        return self.start_ms / 1000.0

    @property
    def end_seconds(self) -> float:
        return self.end_ms / 1000.0

    @property
    def duration_seconds(self) -> float:
        return (self.end_ms - self.start_ms) / 1000.0


def extract_clip(spec: ClipSpec) -> None:
    """
    Extract a clip from source video using FFmpeg.
    Uses stream copy (no re-encode) for speed.
    Source should be the original 2.7K video for best quality.
    """
    (
        ffmpeg
        .input(spec.source_path, ss=spec.start_seconds, to=spec.end_seconds)
        .output(
            spec.output_path,
            vcodec="copy",   # stream copy — no re-encode, instant
            acodec="copy",
        )
        .overwrite_output()
        .run(capture_stdout=True, capture_stderr=True)
    )


def extract_clips_batch(specs: list[ClipSpec]) -> list[str]:
    """
    Extract multiple clips sequentially. Returns list of output paths.
    Skips clips that fail (logs error, continues).
    """
    successful = []
    for spec in specs:
        try:
            extract_clip(spec)
            successful.append(spec.output_path)
        except ffmpeg.Error as e:
            # Log and continue — don't fail the whole batch for one bad clip
            stderr_msg = e.stderr.decode() if e.stderr else "(no stderr)"
            logger.error("Clip extraction failed for %d-%dms: %s", spec.start_ms, spec.end_ms, stderr_msg)
    return successful
