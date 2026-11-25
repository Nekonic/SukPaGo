"""앱 설정(settings.json)과 용어 고치기 목록(glossary.json)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields

from . import userdata
from .languages import TARGET_ORDER
from .text.glossary import Glossary, Rule

SETTINGS_FILE = "settings.json"
GLOSSARY_FILE = "glossary.json"
DEFAULT_GLOSSARY = (
    Rule("노트북 에램", "NotebookLM"),
    Rule("한강 리스크", "할루시네이션 리스크"),
)


@dataclass
class Settings:
    online: bool = True
    langs: list[str] = field(default_factory=lambda: ["mn", "zh"])
    mymemory_email: str = "abcd@gmail.com"
    main_geometry: str | None = None
    display_geometry: str | None = None
    display_font_px: int = 52


def _is_bool(v) -> bool:
    return isinstance(v, bool)


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_str(v) -> bool:
    return isinstance(v, str)


def _is_opt_str(v) -> bool:
    return v is None or isinstance(v, str)


def _is_langs(v) -> bool:
    return (isinstance(v, list) and len(v) > 0
            and all(isinstance(x, str) and x in TARGET_ORDER for x in v))


_CHECKS = {
    "online": _is_bool,
    "langs": _is_langs,
    "mymemory_email": _is_str,
    "main_geometry": _is_opt_str,
    "display_geometry": _is_opt_str,
    "display_font_px": _is_int,
}


def load_settings() -> Settings:
    data = userdata.read_json(SETTINGS_FILE, {})
    if not isinstance(data, dict):
        data = {}
    values = {}
    for f in fields(Settings):
        if f.name in data and _CHECKS[f.name](data[f.name]):
            v = data[f.name]
            if f.name == "langs":
                v = list(v)
            values[f.name] = v
    return Settings(**values)


def save_settings(s: Settings) -> None:
    userdata.write_json(SETTINGS_FILE, asdict(s))


def load_glossary() -> Glossary:
    data = userdata.read_json(GLOSSARY_FILE, None)
    if data is not None:
        try:
            return Glossary.from_json(data)
        except (TypeError, KeyError, ValueError, AttributeError):
            pass
    return Glossary(list(DEFAULT_GLOSSARY))


def save_glossary(g: Glossary) -> None:
    userdata.write_json(GLOSSARY_FILE, g.to_json())
