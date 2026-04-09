"""
Audio excitement signal extraction.
Uses YAMNet (TF Hub) when available; falls back to RMS energy heuristic.
"""
from __future__ import annotations
import subprocess
import numpy as np


def _yamnet_available() -> bool:
    try:
        import tensorflow_hub  # noqa: F401
        return True
    except ImportError:
        return False


class AudioAnalyzer:
    def extract_audio(self, video_path: str, output_path: str) -> bool:
        """Extract mono 16 kHz WAV from video using ffmpeg. Returns True on success."""
        try:
            result = subprocess.run(
                ["ffmpeg", "-y", "-i", video_path, "-ac", "1", "-ar", "16000",
                 "-vn", output_path],
                capture_output=True, timeout=120,
            )
            return result.returncode == 0
        except Exception:
            return False

    def analyze(self, audio_path: str, fps: int = 2) -> list[float]:
        """
        Returns per-frame excitement scores (0.0–1.0) aligned to video FPS.
        Empty list on any failure — callers must handle gracefully.
        """
        try:
            if _yamnet_available():
                return self._analyze_yamnet(audio_path, fps)
            return self._analyze_rms(audio_path, fps)
        except Exception:
            return []

    def _analyze_rms(self, audio_path: str, fps: int) -> list[float]:
        """Fallback: RMS energy per window, normalized to [0, 1]."""
        import wave
        with wave.open(audio_path, "rb") as wf:
            sample_rate = wf.getframerate()
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        window = sample_rate // fps
        scores = []
        for i in range(0, len(samples), window):
            chunk = samples[i:i + window]
            if len(chunk) == 0:
                break
            rms = float(np.sqrt(np.mean(chunk ** 2)))
            scores.append(rms)
        if not scores:
            return []
        max_rms = max(scores) or 1.0
        return [min(s / max_rms, 1.0) for s in scores]

    def _analyze_yamnet(self, audio_path: str, fps: int) -> list[float]:
        """YAMNet-based crowd/impact detection."""
        import tensorflow as tf
        import tensorflow_hub as hub
        model = hub.load("https://tfhub.dev/google/yamnet/1")
        audio = tf.io.read_file(audio_path)
        waveform, _ = tf.audio.decode_wav(audio, desired_channels=1)
        waveform = tf.squeeze(waveform, axis=-1)
        scores, _, _ = model(waveform)
        # Average score across 521 classes per frame → single excitement value
        frame_scores = tf.reduce_max(scores, axis=1).numpy().tolist()
        return [float(s) for s in frame_scores]
