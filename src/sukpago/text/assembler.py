"""음성 인식 조각을 번역하기 좋은 문장으로 정리한다."""

from __future__ import annotations

import re

from .glossary import Glossary

FILLERS = frozenset({"어", "음", "그", "네", "아", "예", "에", "저", "뭐", "자", "응"})
LEADING_FILLERS = frozenset({"어", "음", "아", "에", "응"})
_PUNCT = ".,?!。，？！…~"
_REPEATED_WORD = re.compile(r"(?<!\S)(\S+)(?:\s+\1)+(?!\S)")
_STUTTER = re.compile(r"(\S+?)(\S{2,})\2")
_SPLIT = re.compile(r"(?<=[.?!。？！])\s+|(?<=[요다죠까])\s+")


def _bare(token: str) -> str:
    return token.strip(_PUNCT)


def _nospace_len(s: str) -> int:
    return len(re.sub(r"\s", "", s))


class SentenceAssembler:
    def __init__(self, glossary: Glossary | None = None, *, min_chars: int = 8,
                 max_chars: int = 120, wait_s: float = 3.0) -> None:
        self.glossary = glossary or Glossary()
        self.min_chars = min_chars
        self.max_chars = max_chars
        self.wait_s = wait_s
        self._pending: str | None = None
        self._since = 0.0

    def feed(self, text: str, now: float) -> list[str]:
        cleaned = self.clean(text)
        if not cleaned:
            return []
        if self._pending is not None:
            cleaned = f"{self._pending} {cleaned}"
        else:
            self._since = now
        self._pending = None
        if _nospace_len(cleaned) < self.min_chars:
            self._pending = cleaned
            return []
        return self._split(cleaned)

    def tick(self, now: float) -> list[str]:
        if self._pending is not None and now - self._since >= self.wait_s:
            return self.flush()
        return []

    def flush(self) -> list[str]:
        if self._pending is None:
            return []
        text, self._pending = self._pending, None
        return self._split(text)

    def clean(self, text: str) -> str:
        t = re.sub(r"\s+", " ", text).strip()
        t = _REPEATED_WORD.sub(r"\1", t)
        t = _STUTTER.sub(r"\1\2", t)
        tokens = t.split(" ") if t else []
        if all(not _bare(tok) or _bare(tok) in FILLERS for tok in tokens):
            return ""
        while tokens and _bare(tokens[0]) in LEADING_FILLERS:
            tokens.pop(0)
        while tokens and _bare(tokens[-1]) in LEADING_FILLERS:
            tokens.pop()
        return self.glossary.apply(" ".join(tokens)).strip()

    def _split(self, text: str) -> list[str]:
        if len(text) <= self.max_chars:
            return [text]
        out: list[str] = []
        cur = ""
        for piece in (p for p in _SPLIT.split(text) if p):
            for part in self._wrap(piece):
                if cur and len(cur) + 1 + len(part) > self.max_chars:
                    out.append(cur)
                    cur = part
                else:
                    cur = f"{cur} {part}" if cur else part
        if cur:
            out.append(cur)
        return out

    def _wrap(self, s: str) -> list[str]:
        parts: list[str] = []
        while len(s) > self.max_chars:
            cut = s.rfind(" ", 0, self.max_chars + 1)
            if cut <= 0:
                cut = self.max_chars
            parts.append(s[:cut].strip())
            s = s[cut:].strip()
        if s:
            parts.append(s)
        return parts
