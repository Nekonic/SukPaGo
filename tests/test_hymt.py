from pathlib import Path

import pytest

from sukpago.translate.base import TranslateError
from sukpago.translate.hymt import HyMtTranslator, build_prompt, clean_output


class FakeLlm:
    def __init__(self, content):
        self.content, self.calls = content, []

    def tokenize(self, data, add_bos=False):
        return list(data)

    def create_chat_completion(self, **kw):
        self.calls.append(kw)
        return {"choices": [{"message": {"content": self.content}}]}


def make(content):
    llm, loads = FakeLlm(content), []

    def loader(path, n_ctx, n_threads):
        loads.append((path, n_ctx, n_threads))
        return llm

    return HyMtTranslator(Path("m.gguf"), loader=loader), llm, loads


def test_chinese_uses_chinese_prompt():
    p = build_prompt("집중하세요.", "zh")
    assert p == "将以下文本翻译为中文，注意只需要输出翻译后的结果，不要额外解释：\n\n집중하세요."


def test_mongolian_prompt_asks_for_cyrillic():
    p = build_prompt("집중하세요.", "mn")
    assert p.startswith("Translate the following segment into Mongolian (Cyrillic script")
    assert p.endswith("without additional explanation.\n\n집중하세요.")


def test_clean_output_strips_wrapping_quotes():
    assert clean_output('  "Please focus."  ') == "Please focus."
    assert clean_output("「请集中注意力。」") == "请集中注意力。"
    assert clean_output("Don't stop") == "Don't stop"


def test_request_parameters():
    t, llm, loads = make("Анхаарлаа төвлөрүүл.")
    text = "집중하세요."
    assert t.translate(text, "mn") == "Анхаарлаа төвлөрүүл."
    kw = llm.calls[0]
    assert kw["messages"] == [{"role": "user", "content": build_prompt(text, "mn")}]
    assert (kw["temperature"], kw["top_p"], kw["top_k"], kw["repeat_penalty"]) == (0.7, 0.6, 20, 1.05)
    assert kw["max_tokens"] == len(text.encode("utf-8")) * 3 + 16
    assert loads == [(Path("m.gguf"), 1024, 4)]


def test_empty_output_is_error_and_unload():
    t, _, _ = make("   ")
    with pytest.raises(TranslateError):
        t.translate("x", "en")
    assert t.loaded
    t.unload()
    assert not t.loaded


@pytest.mark.models
def test_real_model(model_path):
    t = HyMtTranslator(model_path("hymt2", "Hy-MT2-1.8B-Q4_K_M.gguf"))
    assert t.translate("집중하세요.", "en")
