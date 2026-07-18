from __future__ import annotations

from pathlib import Path
import wave


def record_wav(path: Path, seconds: float = 6.0, sample_rate: int = 16000) -> Path:
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise RuntimeError(
            "Chưa có thư viện thu âm micro. Hãy chạy: python -m pip install sounddevice"
        ) from exc

    path.parent.mkdir(parents=True, exist_ok=True)
    frames = int(seconds * sample_rate)
    audio = sd.rec(frames, samplerate=sample_rate, channels=1, dtype="int16")
    sd.wait()

    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(audio.tobytes())

    return path
