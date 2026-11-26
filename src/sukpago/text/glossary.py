"""용어 고치기: 잘못 인식된 말을 바른 말로 바꾼다. 띄어쓰기 차이는 무시한다."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    wrong: str
    right: str


def _pattern(wrong: str) -> re.Pattern[str]:
    chars = [re.escape(c) for c in wrong if not c.isspace()]
    return re.compile(r"\s*".join(chars))


def _key(s: str) -> str:
    return re.sub(r"\s", "", s)


class Glossary:
    def __init__(self, rules: list[Rule] | None = None) -> None:
        self._rules: list[Rule] = []
        self._compiled: list[tuple[re.Pattern[str], str, str]] = []
        self._right_pats: list[tuple[str, re.Pattern[str]]] = []
        for r in rules or []:
            self.add(r.wrong, r.right)

    @property
    def rules(self) -> list[Rule]:
        return list(self._rules)

    def add(self, wrong: str, right: str) -> None:
        wrong, right = wrong.strip(), right.strip()
        if not wrong or not right:
            raise ValueError("인식된 말과 바꿀 말은 비어 있으면 안 됩니다")
        self._rules = [r for r in self._rules if r.wrong != wrong] + [Rule(wrong, right)]
        self._compile()

    def remove(self, wrong: str) -> None:
        self._rules = [r for r in self._rules if r.wrong != wrong.strip()]
        self._compile()

    def apply(self, text: str) -> str:
        """이미 바른 말이 된 자리는 다시 바꾸지 않는다(자바 → 자바스크립트를 두 번 적용해도 같음)."""
        for pat, right, wrong_key in self._compiled:
            # 띄어쓰기만 고치는 규칙("쿠버 네티스" → "쿠버네티스")은 바른 말과 틀린 말이 같아 보이므로 보호에서 뺀다.
            done = [m.span() for key, r in self._right_pats if key != wrong_key for m in r.finditer(text)]

            def sub(m: re.Match[str], right: str = right) -> str:
                if any(a <= m.start() and m.end() <= b for a, b in done):
                    return m.group(0)
                return right

            text = pat.sub(sub, text)
        return text

    def wrong_spans(self, text: str) -> list[tuple[int, int]]:
        """고칠 말(틀린 말)과 이미 바른 말이 나온 자리들. 이 안에서 문장을 자르면 용어가 망가진다."""
        spans = [m.span() for pat, _r, _k in self._compiled for m in pat.finditer(text)]
        return spans + [m.span() for _k, pat in self._right_pats for m in pat.finditer(text)]

    def to_json(self) -> list[dict[str, str]]:
        return [{"wrong": r.wrong, "right": r.right} for r in self._rules]

    @classmethod
    def from_json(cls, data: list[dict[str, str]]) -> "Glossary":
        return cls([Rule(d["wrong"], d["right"]) for d in data])

    def _compile(self) -> None:
        ordered = sorted(self._rules, key=lambda r: len(re.sub(r"\s", "", r.wrong)), reverse=True)
        self._compiled = [(_pattern(r.wrong), r.right, _key(r.wrong)) for r in ordered]
        # 바른 말도 띄어쓰기를 무시하고 찾는다("자바 스크립트"도 이미 고쳐진 자리).
        self._right_pats = [(_key(r), _pattern(r)) for r in sorted({r.right for r in self._rules}, key=len, reverse=True)]
