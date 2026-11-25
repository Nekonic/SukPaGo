"""빠른 안내 문장(assets/phrases.json)과 미리 만든 음성 파일 위치."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from . import paths
from .languages import TARGET_ORDER


@dataclass(frozen=True)
class Phrase:
    key: str
    ko: str
    texts: dict[str, str]


def _from_row(row) -> Phrase | None:
    if not isinstance(row, dict):
        return None
    key, ko = row.get("key"), row.get("ko")
    if not isinstance(key, str) or not isinstance(ko, str):
        return None
    texts = {lang: row[lang] for lang in TARGET_ORDER if isinstance(row.get(lang), str)}
    return Phrase(key, ko, texts)


def _load_fixed() -> list[Phrase]:
    data = json.loads((paths.assets_dir() / "phrases.json").read_text(encoding="utf-8"))
    return [p for p in (_from_row(r) for r in data) if p is not None]


def load_all() -> list[Phrase]:
    return _load_fixed()


def audio_path(phrase: Phrase, lang: str) -> Path:
    return paths.assets_dir() / "phrases" / f"{phrase.key}_{lang}.mp3"
