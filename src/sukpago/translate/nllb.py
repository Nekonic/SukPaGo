"""오프라인 번역: NLLB-200 distilled 600M (CTranslate2 int8)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ..languages import SOURCE_NLLB, get
from .base import TranslateError

Loader = Callable[[Path, int], tuple[Any, Any]]


def _default_loader(model_dir: Path, intra_threads: int) -> tuple[Any, Any]:
    import ctranslate2
    import sentencepiece as spm

    sp = spm.SentencePieceProcessor(model_file=str(model_dir / "sentencepiece.bpe.model"))
    tr = ctranslate2.Translator(str(model_dir), device="cpu", compute_type="int8",
                                intra_threads=intra_threads)
    return sp, tr


class NllbTranslator:
    name = "NLLB-600M"

    def __init__(self, model_dir: Path, *, intra_threads: int = 4, beam_size: int = 2,
                 loader: Loader | None = None) -> None:
        self.model_dir = Path(model_dir)
        self.intra_threads = intra_threads
        self.beam_size = beam_size
        self._loader = loader or _default_loader
        self._sp: Any = None
        self._tr: Any = None

    @property
    def loaded(self) -> bool:
        return self._tr is not None

    def translate(self, text: str, lang: str) -> str:
        if self._tr is None:
            self._sp, self._tr = self._loader(self.model_dir, self.intra_threads)
        code = get(lang).nllb
        tokens = self._sp.encode(text, out_type=str)
        result = self._tr.translate_batch(
            [[SOURCE_NLLB, *tokens, "</s>"]],
            target_prefix=[[code]],
            beam_size=self.beam_size,
            max_decoding_length=len(tokens) * 2 + 16,
            no_repeat_ngram_size=3,
            repetition_penalty=1.2,
        )
        hyp = list(result[0].hypotheses[0])
        if hyp and hyp[0] == code:
            hyp = hyp[1:]
        out = self._sp.decode(hyp).replace("⁇", "").strip()
        if not out:
            raise TranslateError("NLLB가 빈 번역을 돌려주었습니다")
        return out

    def unload(self) -> None:
        self._sp = None
        self._tr = None
