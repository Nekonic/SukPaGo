"""화면과 상관없는 계산 (테스트 대상)."""

from __future__ import annotations

FONT_MIN, FONT_MAX, FONT_STEP = 24, 120, 8
MAX_HISTORY = 500


def clamp_font(px: int) -> int:
    return max(FONT_MIN, min(FONT_MAX, int(px)))


def step_font(px: int, delta: int) -> int:
    return clamp_font(px + delta * FONT_STEP)


def ordered_texts(texts: dict[str, str], langs: list[str], order: tuple[str, ...]) -> list[tuple[str, str]]:
    """켜진 언어만 정해진 순서로 (언어, 번역) 목록을 만든다. 번역이 아직 없는 언어는 뺀다."""
    on = set(langs)
    return [(lang, texts[lang]) for lang in order if lang in on and texts.get(lang)]
