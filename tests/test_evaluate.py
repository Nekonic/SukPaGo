import numpy as np

import evaluate
from sukpago.asr.base import AsrEvent


class FakeRec:
    def __init__(self):
        self.n = 0

    def accept(self, samples):
        self.n += 1
        if self.n == 3:
            return [AsrEvent("partial", "오늘은", 0.3)]
        if self.n == 5:
            return [AsrEvent("final", "음 오늘은 광합성을 배울 거예요", 0.5)]
        return []

    def finish(self):
        return [AsrEvent("final", "그렇구나", 1.0)]


def test_run_asr_collects_finals_and_sentences():
    out = evaluate.run_asr(FakeRec(), np.zeros(16000, dtype=np.float32))
    assert out["finals"] == ["음 오늘은 광합성을 배울 거예요", "그렇구나"]
    assert out["sentences"] == ["오늘은 광합성을 배울 거예요", "그렇구나"]
    assert out["audio_s"] == 1.0 and out["compute_s"] >= 0


def test_flags():
    ok = {"mn": "Анхаарлаа төвлөрүүл.", "zh": "请集中注意力。", "en": "Please focus."}
    assert evaluate.flags(ok) == "-"
    assert "몽골어 전통 문자" in evaluate.flags({**ok, "mn": "ᠮᠣᠩᠭᠣᠯ"})
    assert "몽골어 키릴 아님" in evaluate.flags({**ok, "mn": "Mongolian"})
    assert "zh 반복" in evaluate.flags({**ok, "zh": "解释论文解释论文解释论文"})


def test_cell_escapes_pipes_and_newlines():
    assert evaluate.cell("a|b\nc") == "a\\|b c"
