"""화면과 상관없는 계산 (테스트 대상)."""

from __future__ import annotations

FONT_MIN, FONT_MAX, FONT_STEP = 24, 120, 8
MAX_HISTORY = 500


def clamp_font(px: int) -> int:
    return max(FONT_MIN, min(FONT_MAX, int(px)))


def step_font(px: int, delta: int) -> int:
    return clamp_font(px + delta * FONT_STEP)


def level_fraction(dbfs: float) -> float:
    """마이크 소리 크기(dBFS)를 막대 길이 0~1로. −60dBFS 이하는 0, 0dBFS는 1."""
    return max(0.0, min(1.0, (dbfs + 60.0) / 60.0))


def ordered_texts(texts: dict[str, str], langs: list[str], order: tuple[str, ...]) -> list[tuple[str, str]]:
    """켜진 언어만 정해진 순서로 (언어, 번역) 목록을 만든다. 번역이 아직 없는 언어는 뺀다."""
    on = set(langs)
    return [(lang, texts[lang]) for lang in order if lang in on and texts.get(lang)]
