"""사용자 폴더(설정, 용어, 내 문장)의 위치와 JSON 읽기·쓰기."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path


def home() -> Path:
    override = os.environ.get("SUKPAGO_HOME")
    if override:
        path = Path(override)
    elif sys.platform == "win32" and os.environ.get("APPDATA"):
        path = Path(os.environ["APPDATA"]) / "SukPaGo"
    else:
        path = Path.home() / ".sukpago"
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_json(name: str, default):
    try:
        return json.loads((home() / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(name: str, data) -> None:
    target = home() / name
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
