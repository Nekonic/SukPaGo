"""모델·에셋 폴더 위치. PyInstaller exe에서는 exe 옆, 개발 중에는 저장소 루트."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def models_dir() -> Path:
    override = os.environ.get("SUKPAGO_MODELS")
    return Path(override) if override else app_root() / "models"


def assets_dir() -> Path:
    return app_root() / "assets"
