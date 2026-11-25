"""고정 문장(assets/phrases.json)과 내 문장(사용자 폴더의 custom_phrases.json)."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from . import paths, userdata
from .languages import TARGET_ORDER

CUSTOM_FILE = "custom_phrases.json"


@dataclass(frozen=True)
class Phrase:
    key: str
    ko: str
    texts: dict[str, str]
    custom: bool


def _from_row(row, custom: bool) -> Phrase | None:
    if not isinstance(row, dict):
        return None
    key, ko = row.get("key"), row.get("ko")
    if not isinstance(key, str) or not isinstance(ko, str):
        return None
    texts = {lang: row[lang] for lang in TARGET_ORDER if isinstance(row.get(lang), str)}
    return Phrase(key, ko, texts, custom)


def _to_row(p: Phrase) -> dict[str, str]:
    return {"key": p.key, "ko": p.ko, **{lang: p.texts[lang] for lang in TARGET_ORDER if lang in p.texts}}


def _load_fixed() -> list[Phrase]:
    data = json.loads((paths.assets_dir() / "phrases.json").read_text(encoding="utf-8"))
    return [p for p in (_from_row(r, False) for r in data) if p is not None]


def _load_custom() -> list[Phrase]:
    data = userdata.read_json(CUSTOM_FILE, [])
    if not isinstance(data, list):
        return []
    return [p for p in (_from_row(r, True) for r in data) if p is not None]


def _save_custom(items: list[Phrase]) -> None:
    userdata.write_json(CUSTOM_FILE, [_to_row(p) for p in items])


def load_all() -> list[Phrase]:
    return _load_fixed() + _load_custom()


def add_custom(ko: str, texts: dict[str, str]) -> Phrase:
    ko = ko.strip()
    if not ko:
        raise ValueError("문장이 비어 있습니다")
    items = _load_custom()
    used = {p.key for p in items}
    ms = int(time.time() * 1000)
    while f"c{ms:013d}" in used:
        ms += 1
    phrase = Phrase(f"c{ms:013d}", ko,
                    {lang: texts[lang] for lang in TARGET_ORDER if lang in texts}, True)
    _save_custom(items + [phrase])
    return phrase


def remove_custom(key: str) -> None:
    items = _load_custom()
    rest = [p for p in items if p.key != key]
    if len(rest) != len(items):
        _save_custom(rest)
    if not (key.startswith("c") and key[1:].isdigit()):
        return
    folder = userdata.home() / "phrases"
    for lang in TARGET_ORDER:
        (folder / f"{key}_{lang}.mp3").unlink(missing_ok=True)


def audio_path(phrase: Phrase, lang: str) -> Path:
    base = userdata.home() if phrase.custom else paths.assets_dir()
    return base / "phrases" / f"{phrase.key}_{lang}.mp3"
