from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import shutil


def play_audio_file(path: Path) -> None:
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Audio file not found: {path}")

    if sys.platform.startswith("win") and path.suffix.lower() == ".wav":
        import winsound

        # Prefer ffplay when available because some Windows Python builds
        # report winsound success even when no sound reaches the output device.
        ffplay = shutil.which("ffplay.exe")
        if ffplay:
            ffplay_result = subprocess.run(
                [ffplay, "-nodisp", "-autoexit", "-volume", "100", "-loglevel", "error", str(path)],
                capture_output=True,
                text=True,
                check=False,
            )
            if ffplay_result.returncode == 0:
                return

        # SND_SYNC has value 0, but some Python builds do not expose the name.
        try:
            winsound.PlaySound(str(path), winsound.SND_FILENAME)
            return
        except RuntimeError as first_error:
            # SoundPlayer is a Windows fallback for Python builds/devices where
            # winsound rejects an otherwise valid PCM WAV file.
            command = (
                "$player = New-Object System.Media.SoundPlayer; "
                "$player.SoundLocation = $args[0]; $player.Load(); $player.PlaySync()"
            )
            result = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    command,
                    str(path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                return
            detail = (result.stderr or result.stdout).strip()
            ffplay = shutil.which("ffplay.exe")
            if ffplay:
                ffplay_result = subprocess.run(
                    [ffplay, "-nodisp", "-autoexit", "-loglevel", "error", str(path)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if ffplay_result.returncode == 0:
                    return
                ffplay_detail = (ffplay_result.stderr or ffplay_result.stdout).strip()
            else:
                ffplay_detail = "ffplay khong co trong PATH"
            raise RuntimeError(
                f"winsound: {first_error}; SoundPlayer: {detail or 'khong phat duoc'}; "
                f"ffplay: {ffplay_detail or 'khong phat duoc'}"
            ) from first_error

    raise RuntimeError(f"Unsupported audio format for autoplay: {path.suffix}")
