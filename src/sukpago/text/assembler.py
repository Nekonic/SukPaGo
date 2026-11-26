"""음성 인식 조각을 번역하기 좋은 문장으로 정리한다."""

from __future__ import annotations

import re

from .clauses import COPULA, GLUE_AFTER_CUT, JOSA, clause_end, ends_sentence
from .glossary import Glossary

FILLERS = frozenset({"어", "음", "그", "네", "아", "예", "에", "저", "뭐", "자", "응"})
LEADING_FILLERS = frozenset({"어", "음", "아", "에", "응"})
_PUNCT = ".,?!。，？！…~"
_REPEATED_WORD = re.compile(r"(?<!\S)(\S+)(?:\s+\1)+(?!\S)")
_STUTTER = re.compile(r"([가-힣]+?)([가-힣]{2,})\2")  # 한글 말 더듬기만 (숫자·영어는 건드리지 않음)
# 앞 어절이 이미 조사로 끝나면("내용은", "실습실로") 뒤의 "에"는 군말, "가"는 동사(가 봅시다)다.
# "결과·속도·정의"처럼 끝 글자가 조사와 같은 명사가 많아, 헷갈리지 않는 조사 끝만 보고 "에/가"에만 쓴다.
_ENDS_WITH_JOSA = ("은", "는", "을", "를", "에", "로", "에서", "으로", "에게", "한테", "께")
_SPLIT = re.compile(r"(?<=[.?!。？！])\s+|(?<=[요다죠까])\s+")


def _bare(token: str) -> str:
    return token.strip(_PUNCT)


_CONNECTIVE_WORDS = frozenset({"특히", "그리고", "그래서", "그러면", "그런데", "근데", "또", "또는", "그러니까", "하지만", "그러나"})


def _can_glue(left: str, right: str) -> bool:
    """강제로 끊긴 조각 뒤에 조사만 떨어져 나온 경우인가."""
    last = left.split(" ")[-1]
    first = _bare(right.strip().split(" ", 1)[0])
    if ends_sentence(last):
        return False
    if first in GLUE_AFTER_CUT:
        return True
    if COPULA.match(first):
        # "특히", "그리고"처럼 문장을 이어 주는 말이나 연결 어미 뒤에는 서술격 조사가 올 수 없다.
        # 앞말이 조사로 끝나면("선으로") 뒤의 "이었습니다"는 서술격 조사가 아니라 동사 '잇다'다.
        # ("경로·회로"처럼 '로'로 끝나는 명사가 많아, 이 검사는 '잇다'와 헷갈리는 '이었' 꼴에만 쓴다.)
        return (last not in _CONNECTIVE_WORDS and not clause_end(last)
                and not (first.startswith("이었") and last.endswith(_ENDS_WITH_JOSA)))
    if first not in JOSA:
        return False
    return not (first in ("에", "가") and last.endswith(_ENDS_WITH_JOSA))


def _join(left: str, right: str, glue: bool) -> str:
    return f"{left}{right}" if glue else f"{left} {right}"


def _nospace_len(s: str) -> int:
    return len(re.sub(r"\s", "", s))


class SentenceAssembler:
    def __init__(self, glossary: Glossary | None = None, *, min_chars: int = 8,
                 max_chars: int = 120, wait_s: float = 3.0, hold_unfinished_chars: int = 40,
                 max_hold_s: float = 8.0) -> None:
        self.glossary = glossary or Glossary()
        self.min_chars = min_chars
        # 문장이 안 끝난 짧은 조각은 따로 한 줄로 내지 않고 다음 조각과 합친다(최대 wait_s).
        self.hold_unfinished_chars = hold_unfinished_chars
        self.max_hold_s = max_hold_s  # 말하는 중이라도 붙잡아 두는 최대 시간
        self.max_chars = max_chars
        self.wait_s = wait_s
        self._pending: str | None = None
        self._since = 0.0
        self._held_at = 0.0
        self._cut = False  # 붙잡은 조각이 인식기의 강제 끊김(15초)에서 나왔는가

    def feed(self, text: str, now: float, *, cut: bool = False) -> list[str]:
        """확정 조각을 받는다. cut=True는 인식기가 15초에서 강제로 끊은 조각(문장이 안 끝났을 수 있음)."""
        glue = self._pending is not None and self._cut and _can_glue(self._pending, text)
        cleaned = self._tidy(text, keep_josa=glue)
        if not cleaned:
            return []
        if self._pending is not None:
            cleaned = _join(self._pending, cleaned, glue)
        else:
            self._held_at = now
        self._since = now
        self._pending = None
        n = _nospace_len(cleaned)
        unfinished = not ends_sentence(cleaned.split(" ")[-1].strip(_PUNCT))
        if n < self.min_chars or (unfinished and (cut or n < self.hold_unfinished_chars)):
            self._pending, self._cut = cleaned, cut and unfinished
            return []
        return self._emit(cleaned)

    def feed_now(self, text: str) -> list[str]:
        """말하는 도중 먼저 확정한 절: 짧아도 기다리지 않고 (붙잡아 둔 앞 조각과 합쳐) 바로 낸다."""
        glue = self._pending is not None and self._cut and _can_glue(self._pending, text)
        cleaned = self._tidy(text, keep_josa=glue)
        if not cleaned:
            return []
        if self._pending is not None:
            cleaned = _join(self._pending, cleaned, glue)
            self._pending = None
        return self._emit(cleaned)

    @property
    def waiting_for_cut(self) -> bool:
        """강제로 끊긴 조각을 붙잡고 다음 말을 기다리는 중인가."""
        return self._pending is not None and self._cut

    def still_talking(self, now: float) -> None:
        """강사가 아직 말하는 중이면(새 임시 자막) 붙잡아 둔 조각의 대기 시간을 다시 센다."""
        if self._pending is not None:
            self._since = now

    def tick(self, now: float) -> list[str]:
        if self._pending is not None and (now - self._since >= self.wait_s
                                          or now - self._held_at >= self.max_hold_s):
            return self.flush()
        return []

    def flush(self) -> list[str]:
        if self._pending is None:
            return []
        text, self._pending = self._pending, None
        return self._emit(text)

    def clean(self, text: str) -> str:
        return self.glossary.apply(self._tidy(text)).strip()

    def _emit(self, text: str) -> list[str]:
        # 용어 고치기는 조각을 합친 뒤에 적용해야 경계에 걸친 규칙도 고쳐진다.
        text = self.glossary.apply(text).strip()
        return self._split(text) if text else []

    def _tidy(self, text: str, *, keep_josa: bool = False) -> str:
        """공백·반복·군말 정리(용어 고치기 전). keep_josa: 강제로 끊긴 앞 조각 뒤의 조사("에")는 지우지 않는다."""
        t = re.sub(r"\s+", " ", text).strip()
        t = _REPEATED_WORD.sub(r"\1", t)
        t = _STUTTER.sub(r"\1\2", t)
        tokens = t.split(" ") if t else []
        if all(not _bare(tok) or _bare(tok) in FILLERS for tok in tokens) and not (keep_josa and tokens):
            return ""
        while tokens and _bare(tokens[0]) in LEADING_FILLERS:
            if keep_josa and _bare(tokens[0]) in JOSA:
                break
            tokens.pop(0)
        while tokens and _bare(tokens[-1]) in LEADING_FILLERS:
            if keep_josa and len(tokens) == 1 and _bare(tokens[0]) in JOSA:
                break  # 강제로 끊긴 앞 조각에 붙을 조사 "에" 하나만 남았다
            tokens.pop()
        return " ".join(tokens).strip()

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
