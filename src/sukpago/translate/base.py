"""번역 엔진 공통 인터페이스."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class TranslateError(Exception):
    """번역 실패. 라우터는 이 예외를 보고 오프라인으로 넘어간다."""


class QuotaExceeded(TranslateError):
    """온라인 무료 한도를 다 썼다."""


@runtime_checkable
class Translator(Protocol):
    name: str

    def translate(self, text: str, lang: str) -> str: ...


@runtime_checkable
class Unloadable(Protocol):
    def unload(self) -> None: ...
