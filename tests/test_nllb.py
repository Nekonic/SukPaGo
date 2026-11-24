from pathlib import Path

import pytest

from sukpago.translate.base import TranslateError
from sukpago.translate.nllb import NllbTranslator


class FakeSp:
    def encode(self, text, out_type=str):
        return text.split()

    def decode(self, tokens):
        return " ".join(tokens)


class FakeResult:
    def __init__(self, tokens):
        self.hypotheses = [tokens]


class FakeTr:
    def __init__(self, out):
        self.out, self.calls = out, []

    def translate_batch(self, src, **kw):
        self.calls.append((src, kw))
        return [FakeResult(self.out)]


def make(out):
    tr, loads = FakeTr(out), []

    def loader(model_dir, intra_threads):
        loads.append((model_dir, intra_threads))
        return FakeSp(), tr

    return NllbTranslator(Path("m"), loader=loader), tr, loads


def test_request_shape_and_prefix_stripped():
    t, tr, _ = make(["khk_Cyrl", "Анхаарлаа", "төвлөрүүл."])
    assert t.translate("집중 하세요", "mn") == "Анхаарлаа төвлөрүүл."
    src, kw = tr.calls[0]
    assert src == [["kor_Hang", "집중", "하세요", "</s>"]]
    assert kw["target_prefix"] == [["khk_Cyrl"]]
    assert kw["beam_size"] == 2
    assert kw["no_repeat_ngram_size"] == 3
    assert kw["repetition_penalty"] == 1.2
    assert kw["max_decoding_length"] == 2 * 2 + 16


def test_lazy_load_once_and_unload():
    t, _, loads = make(["eng_Latn", "ok"])
    assert not t.loaded and loads == []
    t.translate("a", "en")
    t.translate("b", "en")
    assert loads == [(Path("m"), 4)] and t.loaded
    t.unload()
    assert not t.loaded


def test_unknown_token_removed_and_empty_is_error():
    t, _, _ = make(["zho_Hans", "⁇"])
    with pytest.raises(TranslateError):
        t.translate("a", "zh")


@pytest.mark.models
def test_real_model(model_path):
    out = NllbTranslator(model_path("nllb-600m")).translate("집중하세요.", "en").lower()
    assert "focus" in out or "concentrat" in out
