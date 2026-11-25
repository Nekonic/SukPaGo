"""색과 글꼴. 흰 배경 테마 하나만 둔다."""

from __future__ import annotations

import sys

BG = "#FFFFFF"
TEXT = "#111318"      # 글자
MUTED = "#5B6472"     # 임시 자막 (흰 배경 대비 4.5:1 이상)
ACCENT = "#2563EB"    # 강조
ACCENT_HOVER = "#1D4ED8"
BUTTON = "#F5F7FA"    # 빠른 안내 버튼
BUTTON_HOVER = "#E6EEFC"
BORDER = "#C9D1DC"
WARN = "#9A5B00"      # 안내 문구
RED = "#C62828"       # 녹음 시작 버튼
RED_HOVER = "#A61F1F"
STOP = "#3D4654"      # 녹음 중(멈추기) 버튼
STOP_HOVER = "#2A303A"
MIC_COLORS = {"ok": "#137A45", "quiet": WARN, "silent": WARN, "loud": RED}  # 마이크 소리 막대 색

if sys.platform == "win32":
    FONT_KO, FONT_ZH, FONT_LATIN = "Malgun Gothic", "Microsoft YaHei", "Segoe UI"
elif sys.platform == "darwin":
    FONT_KO, FONT_ZH, FONT_LATIN = "Apple SD Gothic Neo", "PingFang SC", "Helvetica Neue"
else:
    FONT_KO, FONT_ZH, FONT_LATIN = "Noto Sans CJK KR", "Noto Sans CJK SC", "DejaVu Sans"


def family_for(lang: str) -> str:
    """중국어는 중국어 글꼴, 몽골어·영어는 라틴 글꼴, 한국어는 한국어 글꼴."""
    if lang == "zh":
        return FONT_ZH
    if lang in ("mn", "en"):
        return FONT_LATIN
    return FONT_KO
