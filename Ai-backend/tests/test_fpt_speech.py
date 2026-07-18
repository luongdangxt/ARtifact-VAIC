from __future__ import annotations

import unittest

from app.fpt_speech import normalize_wav_header


def _pcm_wav(payload: bytes, *, riff_size: int | None = None, data_size: int | None = None) -> bytes:
    fmt = (
        b"fmt "
        + (16).to_bytes(4, "little")
        + (1).to_bytes(2, "little")
        + (1).to_bytes(2, "little")
        + (22050).to_bytes(4, "little")
        + (44100).to_bytes(4, "little")
        + (2).to_bytes(2, "little")
        + (16).to_bytes(2, "little")
    )
    body = fmt + b"data" + (data_size if data_size is not None else len(payload)).to_bytes(4, "little") + payload
    return b"RIFF" + (riff_size if riff_size is not None else len(body) + 4).to_bytes(4, "little") + b"WAVE" + body


class NormalizeWavHeaderTests(unittest.TestCase):
    def test_repairs_fpt_double_sized_header(self) -> None:
        payload = b"\x01\x00\x02\x00" * 20
        malformed = _pcm_wav(
            payload,
            riff_size=(len(payload) * 2) + 36,
            data_size=len(payload) * 2,
        )

        normalized = normalize_wav_header(malformed)

        self.assertEqual(int.from_bytes(normalized[4:8], "little"), len(normalized) - 8)
        self.assertEqual(int.from_bytes(normalized[40:44], "little"), len(payload))
        self.assertEqual(normalized[44:], payload)

    def test_keeps_valid_audio_payload_unchanged(self) -> None:
        valid = _pcm_wav(b"\x00\x00" * 20)
        self.assertEqual(normalize_wav_header(valid), valid)

    def test_rejects_non_wav_response(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "RIFF/WAVE"):
            normalize_wav_header(b"not audio")


if __name__ == "__main__":
    unittest.main()
