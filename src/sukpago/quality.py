"""번역 결과 품질 검사와 메모리 측정 (평가와 CI 스모크 테스트에서 씀)."""

from __future__ import annotations

import re
import sys
from collections import Counter

_TRAD_MN = re.compile(r"[᠀-᢯]")
_CYRILLIC = re.compile(r"[Ѐ-ӿ]")


def has_traditional_mongolian(text: str) -> bool:
    return bool(_TRAD_MN.search(text))


def is_cyrillic_mongolian(text: str) -> bool:
    return bool(_CYRILLIC.search(text)) and not has_traditional_mongolian(text)


def has_repetition(text: str, n: int = 3, times: int = 3) -> bool:
    stripped = text.strip()
    units = stripped.split() if " " in stripped else list(stripped)
    if len(units) < n * times:
        return False
    counts = Counter(tuple(units[i:i + n]) for i in range(len(units) - n + 1))
    return max(counts.values()) >= times


def peak_rss_mb() -> float:
    if sys.platform == "win32":
        import psutil

        return psutil.Process().memory_info().peak_wset / 2**20
    import resource

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / 2**20 if sys.platform == "darwin" else peak / 1024
