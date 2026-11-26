"""말하는 도중 먼저 번역할 절을 고른다.

임시 자막(partial)이 연속 두 번 같은 앞부분을 보이면 그 부분은 바뀌지 않는다고 본다(LocalAgreement).
그 안에서 연결 어미나 종결 어미로 끝난 어절까지를 먼저 내보낸다. 내보낸 것은 고쳐 쓰지 않고,
확정(final)이 오면 아직 안 내보낸 나머지만 돌려준다.
"""

from __future__ import annotations

import re
from collections.abc import Callable

# 문장이 끝나는 어절(종결 어미)과 절이 끝나는 어절(연결 어미). 짧은 '-고'는 동사 뒤일 때만.
_SENTENCE_END = re.compile(
    r"(거든요|는데요|고요|구요|잖아요|어요|아요|에요|예요|해요|세요|죠|습니다|니다|다|요|까)$")
_CLAUSE_END = re.compile(
    r"(는데|은데|인데|던데|지만|니까|으니|어서|아서|해서|해가지고|가지고|면서|으면|다면|려면|"
    r"하고|있고|되고|었고|았고|였고|않고|없고|이고|하면|되면|있으면|없으면)$")
# '-고 있다/싶다' 같은 보조 용언 앞, '-는 것/수/때' 같은 의존 명사 앞은 절 끝이 아니다.
_AUX_AFTER_GO = ("있", "계", "싶", "말", "나", "보", "주", "드리", "하", "되")
_DEPENDENT = ("것", "거", "수", "때", "줄")


# 강제 끊김 뒤에서만 앞 낱말에 붙이는 말: "도"(보고서+도)와 서술격 조사(관점+입니다).
GLUE_AFTER_CUT = ("도",)
# 서술격 조사는 낱말 전체로 확인한다("이라크", "이다음"은 아님).
# "이란(나라)·이면(裏面)·이거나·이야(감탄)"처럼 따로 쓰이는 낱말과 헷갈리는 꼴은 넣지 않는다.
COPULA = re.compile(r"(입니다(만)?|입니까|이에요|예요|이죠|이지요|이다|이고(요)?|이지만|이니까|이면서|이며|이므로|"
                    r"이거든요|이잖아요|이라(?:[고는면서도든니던네][가-힣]*)?|이었[가-힣]*)[.,?!]*$")

# 인식기가 강제로 끊어 앞 낱말에서 떨어져 나올 수 있는 조사. "만·와·도·이"처럼 따로 쓰이는 낱말은 넣지 않는다.
JOSA = frozenset({"을", "를", "가", "은", "는", "에", "의", "로", "과", "에서", "으로", "에게", "한테"})

# 종결 어미처럼 끝나지만 따로 쓰이는 명사·부사·조사("필요 없다", "다 같이", "아까").
_NOT_ENDING = frozenset({"필요", "중요", "주요", "수요", "소요", "개요", "요", "다", "보다", "바다", "마다",
                         "람다", "판다", "아까", "까"})


def ends_sentence(word: str) -> bool:
    return word not in _NOT_ENDING and bool(_SENTENCE_END.search(word))


def clause_end(word: str) -> bool:
    return bool(_CLAUSE_END.search(word))


def _boundary_kind(word: str, nxt: str) -> str | None:
    """'sentence'(문장 끝), 'clause'(절 끝), 또는 None."""
    if word.endswith("고") and nxt.startswith(_AUX_AFTER_GO):
        return None
    if nxt.startswith(_DEPENDENT):
        return None
    if ends_sentence(word):
        return "sentence"
    if _CLAUSE_END.search(word):
        return "clause"
    return None


def _crosses(words: list[str], j: int, spans: list[tuple[int, int]]) -> bool:
    """어절 j와 j+1 사이(공백 하나로 이은 글에서)가 보호 구간 안에 있는가."""
    gap = len(" ".join(words[:j + 1]))
    return any(a <= gap < b for a, b in spans)


class ClauseCommitter:
    def __init__(self, *, agree: int = 2, lookahead: int = 1, sentence_chars: int = 15,
                 clause_chars: int = 35,
                 protect: Callable[[str], list[tuple[int, int]]] | None = None) -> None:
        self.agree = agree
        self.lookahead = lookahead
        # 한 줄이 너무 짧게 끊기지 않도록: 문장 끝은 이만큼, 절 끝(연결 어미)은 더 길어야 먼저 낸다.
        self.sentence_chars = sentence_chars
        self.clause_chars = clause_chars
        self.protect = protect  # 자르면 안 되는 구간(용어 고치기 대상 등)을 돌려주는 함수
        self.reset()

    def reset(self) -> None:
        self._history: list[list[str]] = []
        self._done = 0  # 이번 발화에서 이미 내보낸 어절 수(임시 자막 기준)
        self._sent = ""  # 이미 내보낸 글자(공백 제외)
        self._stable = 0  # 최근 임시 자막들이 같은 앞 어절 수
        self._words: list[str] = []

    def partial(self, text: str) -> list[str]:
        """새 임시 자막을 받아, 이번에 새로 먼저 내보낼 절(없으면 빈 목록)을 돌려준다."""
        words = text.split()
        self._history = (self._history + [words])[-self.agree:]
        if len(self._history) < self.agree:
            return []
        stable = 0
        for column in zip(*self._history):
            if any(w != column[0] for w in column):
                break
            stable += 1
        self._stable, self._words = stable, words
        cut = None
        spans = self.protect(" ".join(words)) if self.protect else []
        for j in range(self._done, stable - self.lookahead):
            kind = _boundary_kind(words[j], words[j + 1])
            if kind is None or _crosses(words, j, spans):
                continue
            need = self.sentence_chars if kind == "sentence" else self.clause_chars
            if len("".join(words[self._done:j + 1])) >= need:
                cut = j
        if cut is None:
            return []
        clause = " ".join(words[self._done:cut + 1])
        self._done = cut + 1
        self._sent += clause.replace(" ", "")
        return [clause]

    def take_head(self) -> str | None:
        """아직 아무것도 안 내보냈고 첫 어절이 안정됐으면 그 어절만 내보낸다.
        강제로 끊긴 앞 조각("요구사항에 맞")에 이어지는 말("추어서")을 빨리 붙이기 위해 쓴다."""
        n = 2 if self._words and self._words[0] in JOSA else 1  # 조사만 따로 내지 않고 다음 낱말과 함께
        if self._done or self._stable < n + self.lookahead:
            return None
        if self.protect and _crosses(self._words, n - 1, self.protect(" ".join(self._words))):
            return None
        head = " ".join(self._words[:n])
        self._done = n
        self._sent += head.replace(" ", "")
        return head

    def final(self, text: str) -> str:
        """확정 문장에서 아직 안 내보낸 나머지를 돌려주고 다음 발화를 준비한다.

        확정 문장은 띄어쓰기가 임시 자막과 다를 수 있어 어절 수가 아니라 공백을 뺀 글자 수로 자른다."""
        need = len(self._sent)
        self.reset()
        if need == 0:
            return text.strip()
        seen = 0
        for i, ch in enumerate(text):
            if not ch.isspace():
                seen += 1
                if seen == need:
                    return text[i + 1:].strip()
        return ""
