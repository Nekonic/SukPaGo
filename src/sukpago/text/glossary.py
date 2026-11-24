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


class Glossary:
    def __init__(self, rules: list[Rule] | None = None) -> None:
        self._rules: list[Rule] = []
        self._compiled: list[tuple[re.Pattern[str], str]] = []
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
        for pat, right in self._compiled:
            text = pat.sub(lambda _m, r=right: r, text)
        return text

    def to_json(self) -> list[dict[str, str]]:
        return [{"wrong": r.wrong, "right": r.right} for r in self._rules]

    @classmethod
    def from_json(cls, data: list[dict[str, str]]) -> "Glossary":
        return cls([Rule(d["wrong"], d["right"]) for d in data])

    def _compile(self) -> None:
        ordered = sorted(self._rules, key=lambda r: len(re.sub(r"\s", "", r.wrong)), reverse=True)
        self._compiled = [(_pattern(r.wrong), r.right) for r in ordered]
