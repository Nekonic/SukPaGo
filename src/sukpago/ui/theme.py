"""색과 글꼴. 흰 배경의 밝은 테마 하나만 둔다."""

from __future__ import annotations

import sys

BG = "#FFFFFF"
TEXT = "#111318"          # 글자
INK = "#14171C"           # 버튼 글자
MUTED = "#5B6472"         # 보조 글자 (흰 배경 대비 4.5:1 이상)
SUBTLE = "#3D4654"        # 한국어 원문
RECENT = "#2A303A"        # 번역 창의 바로 앞 문장
ACCENT = "#2563EB"        # 강조
ACCENT_HOVER = "#1D4ED8"
ACCENT_SOFT = "#E6EEFC"   # 켜진 토글 배경
ACCENT_INK = "#1A3F8F"    # 켜진 토글 글자
CODE_INK = "#1F4FB0"      # 언어 코드
SELECT_BG = "#EEF4FF"     # 번역 창 선택 문장
HOVER_BG = "#F3F6FA"
CARD = "#F5F7FA"          # 카드
BORDER = "#DDE2E9"        # 테두리
BORDER_STRONG = "#C9D1DC"
INPUT_BORDER = "#B9C2CE"
DIVIDER = "#E3E7ED"
CHIP = "#EEF1F5"
OFF_INK = "#4A5361"
GREEN = "#137A45"
GREEN_SOFT = "#E7F6EE"
GREEN_BORDER = "#2E9E63"
ORANGE = "#9A5B00"
ORANGE_SOFT = "#FFF4E0"
RED = "#C62828"
RED_HOVER = "#A61F1F"

if sys.platform == "win32":
    FONT_KO = "Malgun Gothic"
    FONT_ZH = "Microsoft YaHei"
    FONT_LATIN = "Segoe UI"
elif sys.platform == "darwin":
    FONT_KO = "Apple SD Gothic Neo"
    FONT_ZH = "PingFang SC"
    FONT_LATIN = "Helvetica Neue"
else:
    FONT_KO = "Noto Sans CJK KR"
    FONT_ZH = "Noto Sans CJK SC"
    FONT_LATIN = "DejaVu Sans"

LANG_CODES = {"mn": "MN", "zh": "ZH", "en": "EN", "ko": "KO"}


def family_for(lang: str) -> str:
    """언어에 맞는 글꼴 이름. 중국어는 중국어 글꼴, 몽골어·영어는 라틴 글꼴, 나머지는 한국어 글꼴."""
    if lang == "zh":
        return FONT_ZH
    if lang in ("mn", "en"):
        return FONT_LATIN
    return FONT_KO


def mic_color(state: str) -> str:
    """마이크 상태(asr.mic.classify 결과)의 색."""
    return {"ok": GREEN, "quiet": ORANGE, "silent": ORANGE, "loud": RED}.get(state, MUTED)


MIC_TEXT = {
    "ok": "소리 크기 적당함",
    "quiet": "소리가 너무 작아요 · 마이크를 가까이",
    "silent": "소리가 들리지 않아요 · 마이크를 확인하세요",
    "loud": "소리가 너무 커요 · 마이크를 멀리",
}
