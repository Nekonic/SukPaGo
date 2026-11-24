"""어떤 엔진을 쓸지(engines.json)와, 오프라인 번역 모델을 한 번에 하나만 올리는 관리자."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .languages import TARGET_ORDER
from .translate.base import Translator, Unloadable

ASR_ENGINES = ("zipformer", "sensevoice")
MT_ENGINES = ("hymt", "nllb")


@dataclass(frozen=True)
class EngineConfig:
    asr: str
    offline_mt: dict[str, str]


def parse_engines(data: dict) -> EngineConfig:
    asr = data.get("asr")
    if asr not in ASR_ENGINES:
        raise ValueError(f"asr는 {ASR_ENGINES} 중 하나여야 합니다: {asr!r}")
    mt = data.get("offline_mt") or {}
    missing = [lang for lang in TARGET_ORDER if lang not in mt]
    if missing:
        raise ValueError(f"offline_mt에 언어가 빠졌습니다: {missing}")
    bad = {lang: eng for lang, eng in mt.items() if eng not in MT_ENGINES}
    if bad:
        raise ValueError(f"알 수 없는 번역 엔진: {bad}")
    return EngineConfig(asr=asr, offline_mt={lang: mt[lang] for lang in TARGET_ORDER})


def load_engines(path: Path) -> EngineConfig:
    return parse_engines(json.loads(Path(path).read_text(encoding="utf-8")))


class ModelManager:
    """오프라인 번역 엔진은 메모리 때문에 한 번에 하나만 올린다."""

    def __init__(self, factories: dict[str, Callable[[], Translator]]) -> None:
        self._factories = dict(factories)
        self._active_name: str | None = None
        self._active: Translator | None = None

    @property
    def active_name(self) -> str | None:
        return self._active_name

    def get(self, name: str) -> Translator:
        if name not in self._factories:
            raise KeyError(f"등록되지 않은 번역 엔진: {name!r}")
        if self._active_name != name or self._active is None:
            self.unload()
            self._active = self._factories[name]()
            self._active_name = name
        return self._active

    def unload(self) -> None:
        if isinstance(self._active, Unloadable):
            self._active.unload()
        self._active = None
        self._active_name = None
