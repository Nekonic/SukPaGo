"""화면 배치 계산(순수 함수). 위젯 없이 테스트한다."""

from __future__ import annotations

from . import theme

FONT_MIN = 24
FONT_MAX = 120
FONT_STEP = 8
SIZE_MIN = 18
RECENT_COUNT = 3
INPUT_LIMIT = 500

PREV_SCALES: dict[str, float] = {"작게": 0.55, "보통": 0.75, "크게": 0.9}

_REASONS = {"quota": "한도 초과", "error": "오류"}
_SHORT_ENGINE = {"NLLB-600M": "NLLB", "Hy-MT2-1.8B": "Hy-MT2"}


def clamp_font(px: int) -> int:
    return max(FONT_MIN, min(FONT_MAX, int(px)))


def step_font(px: int, delta: int) -> int:
    """delta의 부호만 본다: +면 8px 크게, -면 8px 작게."""
    step = FONT_STEP if delta > 0 else -FONT_STEP if delta < 0 else 0
    return clamp_font(px + step)


def display_sizes(count: int, size_px: int, prev_scale: float,
                  selected: int | None) -> list[tuple[int, str, str]]:
    """번역 창 문장마다 (글자 크기, 굵기, 색). 0번이 가장 오래된 문장.

    최신 문장(선택이 있으면 선택한 문장)은 설정 크기, 최신 문장 바로 앞 3문장은 prev_scale배,
    더 오래된 문장은 그 0.8배의 흐린 글씨다. 크기는 최소 18px.
    """
    if selected is not None and not 0 <= selected < count:
        selected = None
    recent_px = max(SIZE_MIN, round(size_px * prev_scale))
    older_px = max(SIZE_MIN, round(size_px * prev_scale * 0.8))
    last = count - 1
    out: list[tuple[int, str, str]] = []
    for i in range(count):
        big = i == selected if selected is not None else i == last
        if big:
            out.append((size_px, "bold", theme.TEXT))
        elif last - i <= RECENT_COUNT:
            out.append((recent_px, "bold", theme.RECENT))
        else:
            out.append((older_px, "normal", theme.MUTED))
    return out


def engine_label(engine: str | None, online: bool) -> str:
    if not engine:
        return "MyMemory" if online else "NLLB"
    return _SHORT_ENGINE.get(engine, engine)


def status_text(online: bool, engine: str | None, reason: str | None, mem_mb: float,
                *, asr: str = "Zipformer") -> str:
    """상태 표시줄 문구. 예: "온라인 · 인식 Zipformer · 번역 MyMemory · 메모리 0.6GB"."""
    mt = engine_label(engine, online)
    if reason in _REASONS:
        mt += f" ({_REASONS[reason]})"
    mode = "온라인" if online else "오프라인"
    return f"{mode} · 인식 {asr} · 번역 {mt} · 메모리 {mem_mb / 1024:.1f}GB"


def mic_bar_fraction(dbfs: float) -> float:
    """-60dBFS~0dBFS를 0~1 막대 길이로."""
    return max(0.0, min(1.0, (dbfs + 60.0) / 60.0))


def check_direct_input(text: str, limit: int = INPUT_LIMIT) -> str | None:
    """직접 입력 검사. 문제가 있으면 안내 문구, 없으면 None."""
    t = text.strip()
    if not t:
        return "번역할 문장을 입력하세요."
    if len(t) > limit:
        return f"{limit}자 이하로 입력하세요. (지금 {len(t)}자)"
    return None
