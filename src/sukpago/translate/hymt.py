"""오프라인 번역: Tencent Hy-MT2-1.8B (GGUF Q4_K_M, llama-cpp-python CPU)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ..languages import get
from .base import TranslateError

ZH_PROMPT = "将以下文本翻译为{target}，注意只需要输出翻译后的结果，不要额外解释：\n\n{text}"
XX_PROMPT = "Translate the following segment into {target}, without additional explanation.\n\n{text}"
_QUOTES = (('"', '"'), ("“", "”"), ("「", "」"), ("'", "'"))

Loader = Callable[[Path, int, int], Any]


def build_prompt(text: str, lang: str) -> str:
    template = ZH_PROMPT if lang == "zh" else XX_PROMPT
    return template.format(target=get(lang).hymt_name, text=text)


def clean_output(s: str) -> str:
    s = s.strip()
    for left, right in _QUOTES:
        if len(s) >= 2 and s.startswith(left) and s.endswith(right):
            s = s[len(left):-len(right)].strip()
    return s


def _default_loader(model_path: Path, n_ctx: int, n_threads: int) -> Any:
    from llama_cpp import Llama

    return Llama(model_path=str(model_path), n_ctx=n_ctx, n_threads=n_threads, verbose=False)


class HyMtTranslator:
    name = "Hy-MT2-1.8B"

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

    def translate(self, text: str, lang: str) -> str:
        if self._llm is None:
            self._llm = self._loader(self.model_path, self.n_ctx, self.n_threads)
        n_in = len(self._llm.tokenize(text.encode("utf-8"), add_bos=False))
        res = self._llm.create_chat_completion(
            messages=[{"role": "user", "content": build_prompt(text, lang)}],
            temperature=0.7, top_p=0.6, top_k=20, repeat_penalty=1.05,
            max_tokens=n_in * 3 + 16,
        )
        out = clean_output(res["choices"][0]["message"]["content"] or "")
        if not out:
            raise TranslateError("Hy-MT2가 빈 번역을 돌려주었습니다")
        return out

    def unload(self) -> None:
        self._llm = None
