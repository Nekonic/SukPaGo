"""온라인/오프라인 번역 선택.

- 온라인이 실패하면 그 요청만 오프라인으로 처리한다(reason="error").
- 한도를 넘으면 reset_quota() 전까지 온라인을 건너뛴다(reason="quota").
- 오프라인 모드이거나 온라인 엔진이 없으면 reason="offline"이다.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from ..engines import ModelManager
from .base import QuotaExceeded, TranslateError, Translator


@dataclass(frozen=True)
class RouteResult:
    text: str
    engine: str
    fell_back: bool
    reason: str | None = None


class TranslateRouter:
    def __init__(self, online: Translator | None, models: ModelManager,
                 offline_for: dict[str, str], *, idle_unload_s: float | None = 600.0,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._online = online
        self._models = models
        self._offline_for = dict(offline_for)
        self._quota_exceeded = False
        self._lock = threading.Lock()
        self._idle_unload_s = idle_unload_s
        self._clock = clock
        self._last_offline = 0.0

    @property
    def quota_exceeded(self) -> bool:
        return self._quota_exceeded

    def reset_quota(self) -> None:
        self._quota_exceeded = False

    def translate(self, text: str, lang: str, *, online: bool) -> RouteResult:
        if not online or self._online is None:
            return self._offline(text, lang, False, "offline")
        if self._quota_exceeded:
            return self._offline(text, lang, True, "quota")
        try:
            result = RouteResult(self._online.translate(text, lang), self._online.name, False)
            self._unload_if_idle()
            return result
        except QuotaExceeded:
            self._quota_exceeded = True
            return self._offline(text, lang, True, "quota")
        except TranslateError:
            return self._offline(text, lang, True, "error")

    def _offline(self, text: str, lang: str, fell_back: bool, reason: str) -> RouteResult:
        with self._lock:
            engine = self._models.get(self._offline_for[lang])
            out = engine.translate(text, lang)
            self._last_offline = self._clock()
        return RouteResult(out, engine.name, fell_back, reason)

    def _unload_if_idle(self) -> None:
        """온라인이 잘 될 때, 대체 모델을 오래(기본 10분) 안 썼으면 메모리에서 내린다."""
        if self._idle_unload_s is None:
            return
        with self._lock:
            if (self._models.active_name is not None
                    and self._clock() - self._last_offline >= self._idle_unload_s):
                self._models.unload()
