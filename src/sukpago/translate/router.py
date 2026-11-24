"""온라인/오프라인 번역 선택. 온라인이 실패하면 그 요청만 오프라인으로 처리한다."""

from __future__ import annotations

from dataclasses import dataclass

from ..engines import ModelManager
from .base import TranslateError, Translator


@dataclass(frozen=True)
class RouteResult:
    text: str
    engine: str
    fell_back: bool


class TranslateRouter:
    def __init__(self, online: Translator | None, models: ModelManager,
                 offline_for: dict[str, str]) -> None:
        self._online = online
        self._models = models
        self._offline_for = dict(offline_for)

    def translate(self, text: str, lang: str, *, online: bool) -> RouteResult:
        fell_back = False
        if online and self._online is not None:
            try:
                return RouteResult(self._online.translate(text, lang), self._online.name, False)
            except TranslateError:
                fell_back = True
        engine = self._models.get(self._offline_for[lang])
        return RouteResult(engine.translate(text, lang), engine.name, fell_back)
