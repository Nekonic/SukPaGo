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

    def __init__(self, model_dir: Path, *, intra_threads: int = 4, beam_size: int | None = None,
                 loader: Loader | None = None) -> None:
        self.model_dir = Path(model_dir)
        if "1.3b" in self.model_dir.name.lower():
            self.name = "NLLB-1.3B"
        self.intra_threads = intra_threads
        # 빔 4는 조금 낫지만 실측 지연이 두 배라, 느린 Windows 노트북에서도 2초 안에 들도록 2로 둔다.
        self.beam_size = beam_size if beam_size is not None else 2
        self._loader = loader or _default_loader
        self._sp: Any = None
        self._tr: Any = None

    @property
    def loaded(self) -> bool:
        return self._tr is not None

    def translate(self, text: str, lang: str, src: str = "ko") -> str:
        out = self.translate_many(text, [lang], src)[lang]
        if isinstance(out, Exception):
            raise out
        return out

    def translate_many(self, text: str, langs: list[str], src: str = "ko") -> dict[str, str | TranslateError]:
        """한 문장을 여러 언어로 translate_batch 한 번에 번역한다(언어별로 따로 부르는 것보다 약 2배 빠름).
        한 언어가 비어도 다른 언어는 살리도록, 빈 번역은 그 언어 자리에 TranslateError로 돌려준다."""
        if self._tr is None:
            self._sp, self._tr = self._loader(self.model_dir, self.intra_threads)
        codes = [get(lang).nllb for lang in langs]
        source = SOURCE_NLLB if src == "ko" else get(src).nllb
        tokens = self._sp.encode(text, out_type=str)
        result = self._tr.translate_batch(
            [[source, *tokens, "</s>"] for _ in codes],
            target_prefix=[[code] for code in codes],
            beam_size=self.beam_size,
            max_decoding_length=len(tokens) * 2 + 16,
            no_repeat_ngram_size=3,   # 반복 루프 방지
            length_penalty=1.5,       # 긴 문장 뒷부분을 일찍 끝내 버리는 것을 줄임
            disable_unk=True,         # 드문 한자 자리에 <unk>가 나와 빈칸이 생기는 것을 막음
            # repetition_penalty는 쓰지 않는다: 的·我·们처럼 자주 반복되는 중국어 글자 때문에 문장이 일찍 끝났다.
        )
        out: dict[str, str | TranslateError] = {}
        for lang, code, res in zip(langs, codes, result):
            hyp = list(res.hypotheses[0])
            if hyp and hyp[0] == code:
                hyp = hyp[1:]
            line = self._sp.decode(hyp).replace("⁇", "").strip()
            out[lang] = line if line else TranslateError("NLLB가 빈 번역을 돌려주었습니다")
        return out

    def unload(self) -> None:
        self._sp = None
        self._tr = None
