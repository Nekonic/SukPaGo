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
    assert kw["length_penalty"] == 1.5 and kw["disable_unk"] is True
    assert "repetition_penalty" not in kw
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


def test_source_language_can_be_english():
    t, tr, _ = make(["khk_Cyrl", "Анхаарлаа"])
    t.translate("Please focus", "mn", src="en")
    src, _ = tr.calls[0]
    assert src[0][0] == "eng_Latn"


@pytest.mark.models
def test_real_model(model_path):
    out = NllbTranslator(model_path("nllb-600m")).translate("집중하세요.", "en").lower()
    assert "focus" in out or "concentrat" in out


@pytest.mark.models
@pytest.mark.parametrize("folder", ["nllb-1.3b", "tsengel-1.3b"])
def test_real_1_3b_models(model_path, folder):
    out = NllbTranslator(model_path(folder)).translate("집중하세요.", "en").lower()
    assert "focus" in out or "concentrat" in out


class MultiTr:
    def __init__(self):
        self.calls = []

    def translate_batch(self, src, **kw):
        self.calls.append((src, kw))
        return [FakeResult([p[0], "out", p[0]]) for p in kw["target_prefix"]]


def test_translate_many_one_batch_call_per_language_prefix():
    tr = MultiTr()
    t = NllbTranslator(Path("m"), loader=lambda d, n: (FakeSp(), tr))
    out = t.translate_many("집중 하세요", ["mn", "zh", "en"])
    assert out == {"mn": "out khk_Cyrl", "zh": "out zho_Hans", "en": "out eng_Latn"}
    assert len(tr.calls) == 1
    src, kw = tr.calls[0]
    assert src == [["kor_Hang", "집중", "하세요", "</s>"]] * 3
    assert kw["target_prefix"] == [["khk_Cyrl"], ["zho_Hans"], ["eng_Latn"]]


def test_engine_name_follows_model_folder():
    assert NllbTranslator(Path("models/nllb-1.3b")).name == "NLLB-1.3B"
    assert NllbTranslator(Path("models/nllb-600m")).name == "NLLB-600M"


class OneEmptyTr(MultiTr):
    def translate_batch(self, src, **kw):
        self.calls.append((src, kw))
        return [FakeResult([p[0]] if p[0] == "zho_Hans" else [p[0], "ok"]) for p in kw["target_prefix"]]


def test_one_empty_language_does_not_fail_the_others():
    t = NllbTranslator(Path("m"), loader=lambda d, n: (FakeSp(), OneEmptyTr()))
    out = t.translate_many("네", ["mn", "zh", "en"])
    assert out["mn"] == "ok" and out["en"] == "ok"
    assert isinstance(out["zh"], TranslateError)
    with pytest.raises(TranslateError):
        t.translate("네", "zh")
