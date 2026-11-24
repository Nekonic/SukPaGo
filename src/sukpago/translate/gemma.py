"""오프라인 번역: Google TranslateGemma 4B (GGUF Q4_K_M, llama-cpp-python CPU)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .base import TranslateError
from .hymt import clean_output

LANG_NAMES = {"ko": ("Korean", "ko"), "en": ("English", "en"),
              "zh": ("Chinese", "zh-Hans"), "mn": ("Mongolian", "mn")}

Loader = Callable[[Path, int, int], Any]


def build_prompt(text: str, lang: str, src: str = "ko") -> str:
    s, sc = LANG_NAMES[src]
    t, tc = LANG_NAMES[lang]
    return (
        f"<start_of_turn>user\nYou are a professional {s} ({sc}) to {t} ({tc}) translator. "
        f"Your goal is to accurately convey the meaning and nuances of the original {s} text "
        f"while adhering to {t} grammar, vocabulary, and cultural sensitivities.\n"
        f"Produce only the {t} translation, without any additional explanations or commentary. "
        f"Please translate the following {s} text into {t}:\n\n\n{text.strip()}<end_of_turn>\n"
        f"<start_of_turn>model\n"
    )


def _default_loader(model_path: Path, n_ctx: int, n_threads: int) -> Any:
    from llama_cpp import Llama

    return Llama(model_path=str(model_path), n_ctx=n_ctx, n_threads=n_threads, verbose=False)


class TranslateGemmaTranslator:
    name = "TranslateGemma-4B"

    def __init__(self, model_path: Path, *, n_ctx: int = 1024, n_threads: int = 4,
                 loader: Loader | None = None) -> None:
        self.model_path = Path(model_path)
        self.n_ctx = n_ctx
        self.n_threads = n_threads
        self._loader = loader or _default_loader
        self._llm: Any = None

    @property
    def loaded(self) -> bool:
        return self._llm is not None

    def translate(self, text: str, lang: str, src: str = "ko") -> str:
        if self._llm is None:
            self._llm = self._loader(self.model_path, self.n_ctx, self.n_threads)
        n_in = len(self._llm.tokenize(text.encode("utf-8"), add_bos=False))
        res = self._llm.create_completion(
            prompt=build_prompt(text, lang, src),
            max_tokens=n_in * 3 + 16, temperature=0.0, repeat_penalty=1.05,
            stop=["<end_of_turn>"],
        )
        out = clean_output(res["choices"][0]["text"] or "")
        if not out:
            raise TranslateError("TranslateGemma가 빈 번역을 돌려주었습니다")
        return out

    def unload(self) -> None:
        self._llm = None
