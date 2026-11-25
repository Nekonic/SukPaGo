"""음성 합성 공통 형식."""

from __future__ import annotations

from typing import Protocol


class TtsError(Exception):
    """합성 실패(네트워크, 시간 초과, 빈 오디오 등)."""


class Speaker(Protocol):
    name: str

    def synth(self, text: str, lang: str) -> bytes:
        """mp3 바이트를 돌려준다. 실패하면 TtsError."""
        ...
