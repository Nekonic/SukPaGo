"""영어를 거쳐 번역한다: 한국어 → 영어 → 대상 언어 (NLLB는 영어→몽골어 점수가 더 높음)."""

from __future__ import annotations

from typing import Any

from .base import Unloadable


class PivotTranslator:
    def __init__(self, engine: Any, *, name: str, pivot_langs: tuple[str, ...] = ("mn",)) -> None:
        self.engine = engine
        self.name = name
        self.pivot_langs = tuple(pivot_langs)

    def translate(self, text: str, lang: str) -> str:
        if lang not in self.pivot_langs:
            return self.engine.translate(text, lang)
        english = self.engine.translate(text, "en")
        return self.engine.translate(english, lang, src="en")

    def unload(self) -> None:
        if isinstance(self.engine, Unloadable):
            self.engine.unload()
