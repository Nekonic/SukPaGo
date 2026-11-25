"""edge-tts(무료, 키 없음) 음성 합성."""

from __future__ import annotations

import asyncio

from sukpago import languages
from sukpago.tts.base import TtsError


class EdgeSpeaker:
    name = "edge-tts"

    def __init__(self, *, timeout: float = 10.0, communicate=None):
        self.timeout = timeout
        self._communicate = communicate

    def synth(self, text: str, lang: str) -> bytes:
        try:
            voice = languages.get(lang).edge_voice
        except KeyError as e:
            raise TtsError(str(e)) from None
        try:
            # 이벤트 루프는 부른 스레드에서 새로 돌린다.
            return asyncio.run(asyncio.wait_for(self._collect(text, voice), self.timeout))
        except TtsError:
            raise
        except TimeoutError:
            raise TtsError(f"edge-tts 시간 초과({self.timeout:g}초)") from None
        except Exception as e:
            raise TtsError(f"edge-tts 실패: {e}") from e

    async def _collect(self, text: str, voice: str) -> bytes:
        communicate = self._communicate
        if communicate is None:
            import edge_tts

            communicate = edge_tts.Communicate
        buf = bytearray()
        async for chunk in communicate(text, voice).stream():
            if chunk.get("type") == "audio" and chunk.get("data"):
                buf += chunk["data"]
        if not buf:
            raise TtsError("edge-tts가 빈 오디오를 돌려줌")
        return bytes(buf)
