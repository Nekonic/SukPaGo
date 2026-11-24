from pathlib import Path

import pytest

from sukpago.translate.base import TranslateError
from sukpago.translate.gemma import TranslateGemmaTranslator, build_prompt


class FakeLlm:
    def __init__(self, text):
        self.text, self.calls = text, []

    def tokenize(self, data, add_bos=False):
        return list(data)

    def create_completion(self, **kw):
        self.calls.append(kw)
        return {"choices": [{"text": self.text}]}


def make(text):
    llm, loads = FakeLlm(text), []

    def loader(path, n_ctx, n_threads):
        loads.append((path, n_ctx, n_threads))
        return llm

    return TranslateGemmaTranslator(Path("g.gguf"), loader=loader), llm, loads


def test_prompt_matches_gguf_template():
    assert build_prompt("집중하세요.", "mn") == (
        "<start_of_turn>user\nYou are a professional Korean (ko) to Mongolian (mn) translator. "
        "Your goal is to accurately convey the meaning and nuances of the original Korean text "
        "while adhering to Mongolian grammar, vocabulary, and cultural sensitivities.\n"
        "Produce only the Mongolian translation, without any additional explanations or commentary. "
        "Please translate the following Korean text into Mongolian:\n\n\n집중하세요.<end_of_turn>\n"
        "<start_of_turn>model\n"
    )


def test_chinese_code_and_english_source():
    p = build_prompt("Focus.", "zh", src="en")
    assert "English (en) to Chinese (zh-Hans)" in p


def test_request_parameters_and_cleanup():
    t, llm, loads = make("  Please focus.  ")
    assert t.translate("집중하세요.", "en") == "Please focus."
    kw = llm.calls[0]
    assert kw["prompt"] == build_prompt("집중하세요.", "en")
    assert kw["stop"] == ["<end_of_turn>"]
    assert kw["temperature"] == 0.0 and kw["repeat_penalty"] == 1.05
    assert kw["max_tokens"] == len("집중하세요.".encode("utf-8")) * 3 + 16
    assert loads == [(Path("g.gguf"), 1024, 4)]


def test_empty_is_error_and_unload():
    t, _, _ = make(" ")
    with pytest.raises(TranslateError):
        t.translate("x", "zh")
    t.unload()
    assert not t.loaded


@pytest.mark.models
def test_real_model(model_path):
    t = TranslateGemmaTranslator(model_path("tgemma", "translategemma-4b-it.Q4_K_M.gguf"))
    assert t.translate("집중하세요.", "en")
