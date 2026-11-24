# 석파고 계획 1b: 오프라인 강화 2차 평가 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 메모리 상한을 4GB로 올린 조건에서 더 큰 오프라인 번역·음성 인식 후보를 엔진으로 추가하고, 같은 강의 녹음으로 2차 평가해 `assets/engines.json`을 정한다.

**Architecture:** 계획 1의 구조(`Translator`/`Recognizer` 프로토콜, 가짜 객체 주입 테스트, `models` 테스트 자동 건너뛰기, `tools/evaluate.py` 하위 프로세스 측정)를 그대로 쓴다. 새로 추가하는 것은 다음과 같다.
- **NLLB 원문 언어 지정:** 영어를 원문으로 넣을 수 있게 한다.
- **영어 경유 번역기(`PivotTranslator`):** 한국어 → 영어 → 대상 언어로 두 번 번역한다.
- **TranslateGemma 번역기:** llama-cpp-python으로 돌린다.
- **VAD 공통 클래스와 Qwen3-ASR 인식기:** SenseVoice와 Qwen3-ASR가 VAD 구간 처리를 함께 쓴다.

**Tech Stack:** 계획 1과 같다. 의존성은 추가하지 않는다.

**배경:** 1차 평가 결과는 다음과 같았다. 2차 후보를 고른 근거는 설계 문서 3장과 2026-11-24 조사 결과다.
- Hy-MT2는 몽골어 칸에 러시아어·세르비아어를 냈다.
- NLLB-600M은 몽골어는 맞지만 뜻이 많이 틀렸다.
- Zipformer는 sherpa-onnx 버그로 띄어쓰기가 사라졌다(`3c1dbbe`에서 고침).

| 역할 | 2차 후보 | 근거 |
|---|---|---|
| 번역 | NLLB-200 distilled 1.3B (`OpenNMT/nllb-200-distilled-1.3B-ct2-int8`) | Meta FLORES-200 kor→khk chrF++ 35.9 (600M은 32.2) |
| 번역 | 몽골어 특화 NLLB 1.3B (`Tsengel-mn/nllb-1.3b-mongolian-ct2-int8`) | 영어↔몽골어 71만 문장으로 추가 학습. 공개 수치는 없음 |
| 번역 | TranslateGemma 4B Q4_K_M (`mradermacher/translategemma-4b-it-GGUF`) | 중국어·영어가 강할 것으로 예상. 몽골어는 영어→몽골어 학습만 있음 |
| 번역 방식 | 위 모델 각각을 한국어 → 영어 → 몽골어로 | NLLB의 영어→몽골어 점수가 한국어→몽골어보다 4~6점 높음 |
| 음성 인식 | Qwen3-ASR 0.6B int8 (sherpa-onnx `from_qwen3_asr`) | FLEURS ko CER 3.72, 대화 10.31, 문장부호와 핫워드 지원 |

Nemotron 3.5 스트리밍은 sherpa-onnx 1.13.8에 로더가 없어서 이번 평가에서 뺀다. 2.0.x로 올리면 Piper 영어 TTS가 실패하기 때문이다.

## Global Constraints

- 계획 1의 Global Constraints를 그대로 따른다. 예외는 메모리 하나다.
- **메모리 상한:** 오프라인으로 전부 켰을 때 4GB 이하. TTS와 화면 몫(약 0.5GB)을 빼면, 음성 인식과 번역을 합친 목표는 3.5GB(3500MB) 이하다.
- `sherpa-onnx==1.13.8`과 `sherpa-onnx-core==1.13.8`은 바꾸지 않는다.
- 새 의존성을 추가하지 않는다. `pyproject.toml`과 `uv.lock`은 건드리지 않는다.
- 평가용 핫워드 목록은 강의 내용을 보고 정한 것이라 결과가 유리하게 나온다. 그래서 핫워드 없는 Qwen3-ASR과 따로 비교한다.

---

### Task R1: 2차 후보 모델 목록 (models.lock.json)

**Files:**
- Modify: `tools/models.lock.json` (`models` 안에 항목 4개 추가), `tests/test_download_models.py` (모델 이름 집합)

**Interfaces:**
- Produces: 모델 폴더 `models/nllb-1.3b/`, `models/tsengel-1.3b/`, `models/tgemma/translategemma-4b-it.Q4_K_M.gguf`, `models/qwen3-asr/` (`conv_frontend.onnx`, `encoder.int8.onnx`, `decoder.int8.onnx`, `tokenizer/`)

- [ ] **Step 1: 테스트의 모델 이름 집합을 바꿔 실패를 확인**

`tests/test_download_models.py`의 `test_lock_file_is_complete`에서 집합을 바꾼다.

```python
    assert set(lock) == {"nllb-600m", "hymt2-q4", "zipformer-ko", "sensevoice-ko", "silero-vad",
                         "nllb-1.3b", "tsengel-1.3b", "tgemma-q4", "qwen3-asr"}
```

Run: `uv run pytest tests/test_download_models.py -q`
Expected: 1 failed

- [ ] **Step 2: `tools/models.lock.json`의 `models`에 항목 추가**

값은 2026-11-24에 Hugging Face API, GitHub 릴리스 digest, 직접 받은 파일의 SHA256으로 확인했다. OpenNMT 저장소에는 `sentencepiece.bpe.model`이 없다. 그래서 NLLB 공통 토크나이저를 JustFrederik 저장소에서 받는다(SHA256이 Tsengel 저장소의 파일과 같음).

```json
    "nllb-1.3b": {
      "dir": "nllb-1.3b",
      "files": [
        {"name": "config.json", "size": 1071,
         "sha256": "bb11352c2579e31d4251500cd3d813beb6ab083c8a60268db52e9698c1c9cda2",
         "url": "https://huggingface.co/OpenNMT/nllb-200-distilled-1.3B-ct2-int8/resolve/70f572adafa4794890ce7826156a4209717855af/config.json"},
        {"name": "model.bin", "size": 1377755738,
         "sha256": "89dc4b9eb7f4dcd3ff36023c9b1c55fcecb47ddc0df97ab31b068ef9cf194940",
         "url": "https://huggingface.co/OpenNMT/nllb-200-distilled-1.3B-ct2-int8/resolve/70f572adafa4794890ce7826156a4209717855af/model.bin"},
        {"name": "shared_vocabulary.json", "size": 5921176,
         "sha256": "af53bfd0e6f726209e7325e45b87ab3b14e5856f7d42d7b9be91de3287c45267",
         "url": "https://huggingface.co/OpenNMT/nllb-200-distilled-1.3B-ct2-int8/resolve/70f572adafa4794890ce7826156a4209717855af/shared_vocabulary.json"},
        {"name": "sentencepiece.bpe.model", "size": 4852054,
         "sha256": "14bb8dfb35c0ffdea7bc01e56cea38b9e3d5efcdcb9c251d6b40538e1aab555a",
         "url": "https://huggingface.co/JustFrederik/nllb-200-distilled-600M-ct2-int8/resolve/302d78f00e6fdb50a1064059df7c392b735e9d05/sentencepiece.bpe.model"}
      ]
    },
    "tsengel-1.3b": {
      "dir": "tsengel-1.3b",
      "files": [
        {"name": "config.json", "size": 223,
         "sha256": "8f6496adfc930cbfecbe8281112197705c488fab47d34b4829b06d7f478909af",
         "url": "https://huggingface.co/Tsengel-mn/nllb-1.3b-mongolian-ct2-int8/resolve/d012f6d8d12f15847e035abe7cf7125d868daa0a/config.json"},
        {"name": "model.bin", "size": 1377755777,
         "sha256": "3a4b0a49ca3710fb9fa5c8506075622d04547fc904bc21a263d5dd0171f69c9d",
         "url": "https://huggingface.co/Tsengel-mn/nllb-1.3b-mongolian-ct2-int8/resolve/d012f6d8d12f15847e035abe7cf7125d868daa0a/model.bin"},
        {"name": "shared_vocabulary.json", "size": 5921176,
         "sha256": "af53bfd0e6f726209e7325e45b87ab3b14e5856f7d42d7b9be91de3287c45267",
         "url": "https://huggingface.co/Tsengel-mn/nllb-1.3b-mongolian-ct2-int8/resolve/d012f6d8d12f15847e035abe7cf7125d868daa0a/shared_vocabulary.json"},
        {"name": "sentencepiece.bpe.model", "size": 4852054,
         "sha256": "14bb8dfb35c0ffdea7bc01e56cea38b9e3d5efcdcb9c251d6b40538e1aab555a",
         "url": "https://huggingface.co/Tsengel-mn/nllb-1.3b-mongolian-ct2-int8/resolve/d012f6d8d12f15847e035abe7cf7125d868daa0a/sentencepiece.bpe.model"}
      ]
    },
    "tgemma-q4": {
      "dir": "tgemma",
      "files": [
        {"name": "translategemma-4b-it.Q4_K_M.gguf", "size": 2489909760,
         "sha256": "81200d03e843d2ec1ece6eeafe7d13cb6e5211e1fcd336ade55790b683a08330",
         "url": "https://huggingface.co/mradermacher/translategemma-4b-it-GGUF/resolve/d37868f759d2f817a43d28dd80cf9f982ffa62fd/translategemma-4b-it.Q4_K_M.gguf"}
      ]
    },
    "qwen3-asr": {
      "dir": "qwen3-asr",
      "archive": {"size": 878702423,
        "sha256": "393f8a14e2f5fb96746aaab342997a40641001fbd5bf9592a080a8329178ee96",
        "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-qwen3-asr-0.6B-int8-2026-03-25.tar.bz2"}
    }
```

- [ ] **Step 3: 테스트 통과 확인 후 모델 받기**

Run: `uv run pytest tests/test_download_models.py -q`
Expected: 5 passed

Run: `uv run python tools/download_models.py nllb-1.3b tsengel-1.3b tgemma-q4 qwen3-asr`
Expected: 전부 "받음"으로 끝난다(약 6.1GB).

- [ ] **Step 4: 커밋**

```bash
git add tools/models.lock.json tests/test_download_models.py
git commit -m "chore: 2차 평가 후보 모델 4개를 모델 목록에 추가"
```

---

### Task R2: 원문 언어 지정, 영어 경유 번역, TranslateGemma

**Files:**
- Modify: `src/sukpago/translate/nllb.py`, `tests/test_nllb.py`
- Create: `src/sukpago/translate/pivot.py`, `src/sukpago/translate/gemma.py`, `tests/test_pivot.py`, `tests/test_gemma.py`

**Interfaces:**
- Consumes: `languages.get`, `SOURCE_NLLB`, `TranslateError`, `Unloadable`, `hymt.clean_output`
- Produces:
  - `NllbTranslator.translate(text, lang, src="ko")`: `src`가 `"ko"`면 `kor_Hang`, 아니면 `get(src).nllb`를 원문 코드로 쓴다.
  - `PivotTranslator(engine, *, name: str, pivot_langs: tuple[str, ...] = ("mn",))`
    - `.translate(text, lang)`: `lang`이 `pivot_langs`에 있으면 `engine.translate(text, "en")`의 결과를 다시 `engine.translate(en, lang, src="en")`에 넣는다. 그 밖의 언어는 `engine.translate(text, lang)`로 바로 번역한다.
    - `.unload()`
  - `TranslateGemmaTranslator(model_path, *, n_ctx=1024, n_threads=4, loader=None)`, `name = "TranslateGemma-4B"`
    - `.translate(text, lang, src="ko")`, `.unload()`, `.loaded`
  - `gemma.build_prompt(text, lang, src="ko") -> str`
  - `gemma.LANG_NAMES = {"ko": ("Korean", "ko"), "en": ("English", "en"), "zh": ("Chinese", "zh-Hans"), "mn": ("Mongolian", "mn")}`

TranslateGemma GGUF에 들어 있는 채팅 템플릿은 `content`에 `source_lang_code`·`target_lang_code`가 든 특수 구조를 요구한다. 그래서 템플릿이 만드는 문자열을 그대로 직접 만들어 `create_completion`에 넣는다. 이 문자열은 2026-11-24에 GGUF 헤더에서 직접 확인했다. BOS 토큰은 llama-cpp-python이 붙인다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_nllb.py` 끝에 추가:

```python
def test_source_language_can_be_english():
    t, tr, _ = make(["khk_Cyrl", "Анхаарлаа"])
    t.translate("Please focus", "mn", src="en")
    src, _ = tr.calls[0]
    assert src[0][0] == "eng_Latn"
```

`tests/test_pivot.py`:

```python
from sukpago.translate.pivot import PivotTranslator


class Eng:
    name = "E"

    def __init__(self):
        self.calls, self.unloaded = [], False

    def translate(self, text, lang, src="ko"):
        self.calls.append((text, lang, src))
        return f"{src}>{lang}:{text}"

    def unload(self):
        self.unloaded = True


def test_mongolian_goes_through_english():
    e = Eng()
    p = PivotTranslator(e, name="E-pivot")
    assert p.translate("안녕", "mn") == "en>mn:ko>en:안녕"
    assert e.calls == [("안녕", "en", "ko"), ("ko>en:안녕", "mn", "en")]
    assert p.name == "E-pivot"


def test_other_languages_are_direct():
    e = Eng()
    p = PivotTranslator(e, name="E-pivot")
    assert p.translate("안녕", "zh") == "ko>zh:안녕"
    assert p.translate("안녕", "en") == "ko>en:안녕"


def test_unload_passes_through():
    e = Eng()
    PivotTranslator(e, name="x").unload()
    assert e.unloaded
```

`tests/test_gemma.py`:

```python
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
```

`tests/test_nllb.py`의 실제 모델 테스트 옆에 1.3B 테스트를 추가:

```python
@pytest.mark.models
@pytest.mark.parametrize("folder", ["nllb-1.3b", "tsengel-1.3b"])
def test_real_1_3b_models(model_path, folder):
    out = NllbTranslator(model_path(folder)).translate("집중하세요.", "en").lower()
    assert "focus" in out or "concentrat" in out
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `uv run pytest tests/test_nllb.py tests/test_pivot.py tests/test_gemma.py -q`
Expected: FAIL (`translate()` got an unexpected keyword argument 'src', 그리고 `ModuleNotFoundError`)

- [ ] **Step 3: 구현**

`src/sukpago/translate/nllb.py`에서 두 군데를 고친다.

```python
    def translate(self, text: str, lang: str, src: str = "ko") -> str:
        if self._tr is None:
            self._sp, self._tr = self._loader(self.model_dir, self.intra_threads)
        code = get(lang).nllb
        source = SOURCE_NLLB if src == "ko" else get(src).nllb
        tokens = self._sp.encode(text, out_type=str)
        result = self._tr.translate_batch(
            [[source, *tokens, "</s>"]],
```

(나머지 줄은 그대로 둔다.)

`src/sukpago/translate/pivot.py`:

```python
"""영어를 거쳐 번역한다: 한국어 → 영어 → 대상 언어 (NLLB는 영어→몽골어 점수가 더 높음)."""

from __future__ import annotations

from typing import Any

from .base import Unloadable


class PivotTranslator:
    def __init__(self, engine: Any, *, name: str, pivot_langs: tuple[str, ...] = ("mn",)) -> None:
        self.engine = engine
        self.name = name
        self.pivot_langs = tuple(pivot_langs)

    def translate(self, text: str, lang: str) -> str:
        if lang not in self.pivot_langs:
            return self.engine.translate(text, lang)
        english = self.engine.translate(text, "en")
        return self.engine.translate(english, lang, src="en")

    def unload(self) -> None:
        if isinstance(self.engine, Unloadable):
            self.engine.unload()
```

`src/sukpago/translate/gemma.py`:

```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_nllb.py tests/test_pivot.py tests/test_gemma.py -v`
Expected:
- 모델이 없으면: nllb 4 passed 3 skipped, pivot 3 passed, gemma 4 passed 1 skipped
- 모델이 있으면: 모두 passed

- [ ] **Step 5: 커밋**

```bash
git add src/sukpago/translate tests/test_nllb.py tests/test_pivot.py tests/test_gemma.py
git commit -m "feat: 영어 경유 번역과 TranslateGemma 번역 추가"
```

---

### Task R3: VAD 공통 클래스와 Qwen3-ASR

**Files:**
- Create: `src/sukpago/asr/vad.py`, `src/sukpago/asr/qwen3.py`, `tests/test_asr_vad.py`
- Modify: `src/sukpago/asr/sensevoice.py`, `tests/test_asr_engines.py`

**Interfaces:**
- Consumes: `SAMPLE_RATE`, `AsrEvent`, `Framer` (`asr/base.py`)
- Produces:
  - `VadSegmentedRecognizer(vad_model: Path | None, *, min_silence=0.5, max_speech=15.0, vad=None)`
    - `vad`를 주면 그 객체를 쓴다(테스트용). 객체는 `accept_waveform`, `flush`, `empty`, `front`(`.samples`, `.start`), `pop`을 가져야 한다.
    - `.accept(samples)`, `.finish()`
    - 하위 클래스가 `_decode(samples: np.ndarray) -> str`를 구현한다.
  - `SenseVoiceRecognizer(model_dir, vad_model, *, num_threads=2, min_silence=0.5, max_speech=15.0)`: 이제 `VadSegmentedRecognizer`를 상속한다. 동작은 같다.
  - `Qwen3AsrRecognizer(model_dir, vad_model, *, hotwords: tuple[str, ...] = (), num_threads=2, min_silence=0.5, max_speech=15.0)`, `name = "Qwen3-ASR"`
    - 모델 폴더: `conv_frontend.onnx`, `encoder.int8.onnx`, `decoder.int8.onnx`, `tokenizer/`
    - 구간마다 `stream.set_option("language", "Korean")`
    - `max_new_tokens=256`. 구간은 15초 이하로 자른다(sherpa-onnx issue #4034: 30초 구간에서 출력이 빠짐).

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_asr_vad.py`:

```python
import numpy as np

from sukpago.asr.vad import VadSegmentedRecognizer


class Seg:
    def __init__(self, start, samples):
        self.start, self.samples = start, samples


class FakeVad:
    """프레임을 3개 받을 때마다 구간 하나를 낸다."""

    def __init__(self):
        self.frames, self.queue, self.flushed = [], [], False

    def accept_waveform(self, frame):
        self.frames.append(len(frame))
        if len(self.frames) % 3 == 0:
            self.queue.append(Seg(16000 * (len(self.frames) - 3) // 31, np.zeros(1536, np.float32)))

    def flush(self):
        self.flushed = True
        self.queue.append(Seg(0, np.zeros(10, np.float32)))

    def empty(self):
        return not self.queue

    @property
    def front(self):
        return self.queue[0]

    def pop(self):
        self.queue.pop(0)


class Echo(VadSegmentedRecognizer):
    name = "echo"

    def __init__(self, vad):
        super().__init__(None, vad=vad)
        self.n = 0

    def _decode(self, samples):
        self.n += 1
        return f" 문장{self.n} " if len(samples) > 100 else ""


def test_frames_of_512_and_finals_from_segments():
    vad = FakeVad()
    rec = Echo(vad)
    events = rec.accept(np.zeros(1600, np.float32))
    assert vad.frames == [512, 512, 512]
    assert [(e.kind, e.text) for e in events] == [("final", "문장1")]
    events = rec.finish()
    assert vad.flushed and vad.frames[-1] == 1600 - 3 * 512
    assert events == []
```

`tests/test_asr_engines.py` 끝에 추가:

```python
@pytest.mark.models
@pytest.mark.parametrize("hotwords", [(), ("NotebookLM", "할루시네이션")])
def test_qwen3_recognizes_korean(model_path, hotwords):
    from sukpago.asr.qwen3 import Qwen3AsrRecognizer

    rec = Qwen3AsrRecognizer(model_path("qwen3-asr"), model_path("vad", "silero_vad.onnx"),
                             hotwords=hotwords)
    text = run(rec, load_wav_16k_mono(model_path("sensevoice", "test_wavs", "ko.wav")))
    assert HANGUL.search(text), text
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `uv run pytest tests/test_asr_vad.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'sukpago.asr.vad'`)

- [ ] **Step 3: 구현**

`src/sukpago/asr/vad.py`:

```python
"""silero VAD로 말 구간을 자른 뒤 구간마다 인식하는 엔진의 공통 부분."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from .base import SAMPLE_RATE, AsrEvent, Framer


class VadSegmentedRecognizer:
    name = "vad"

    def __init__(self, vad_model: Path | None, *, min_silence: float = 0.5,
                 max_speech: float = 15.0, vad: Any = None) -> None:
        if vad is None:
            import sherpa_onnx

            cfg = sherpa_onnx.VadModelConfig()
            cfg.silero_vad.model = str(vad_model)
            cfg.silero_vad.min_silence_duration = min_silence
            cfg.silero_vad.max_speech_duration = max_speech
            cfg.sample_rate = SAMPLE_RATE
            vad = sherpa_onnx.VoiceActivityDetector(cfg, buffer_size_in_seconds=60)
        self._vad = vad
        self._framer = Framer(512)

    def _decode(self, samples: np.ndarray) -> str:
        raise NotImplementedError

    def accept(self, samples: np.ndarray) -> list[AsrEvent]:
        for frame in self._framer.push(samples):
            self._vad.accept_waveform(frame)
        return self._drain()

    def finish(self) -> list[AsrEvent]:
        rest = self._framer.rest()
        if len(rest):
            self._vad.accept_waveform(rest)
        self._vad.flush()
        return self._drain()

    def _drain(self) -> list[AsrEvent]:
        events: list[AsrEvent] = []
        while not self._vad.empty():
            seg = self._vad.front
            text = self._decode(np.asarray(seg.samples, dtype=np.float32)).strip()
            if text:
                events.append(AsrEvent("final", text, (seg.start + len(seg.samples)) / SAMPLE_RATE))
            self._vad.pop()
        return events
```

`src/sukpago/asr/sensevoice.py` 전체를 다음으로 바꾼다.

```python
"""문장 단위 한국어 음성 인식: silero VAD + SenseVoice 2024-07-17 (sherpa-onnx int8)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .base import SAMPLE_RATE
from .vad import VadSegmentedRecognizer


class SenseVoiceRecognizer(VadSegmentedRecognizer):
    name = "SenseVoice"

    def __init__(self, model_dir: Path, vad_model: Path, *, num_threads: int = 2,
                 min_silence: float = 0.5, max_speech: float = 15.0) -> None:
        import sherpa_onnx

        model_dir = Path(model_dir)
        self._rec = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=str(model_dir / "model.int8.onnx"), tokens=str(model_dir / "tokens.txt"),
            language="ko", use_itn=True, num_threads=num_threads,
        )
        super().__init__(vad_model, min_silence=min_silence, max_speech=max_speech)

    def _decode(self, samples: np.ndarray) -> str:
        stream = self._rec.create_stream()
        stream.accept_waveform(SAMPLE_RATE, samples)
        self._rec.decode_stream(stream)
        return stream.result.text
```

`src/sukpago/asr/qwen3.py`:

```python
"""문장 단위 한국어 음성 인식: silero VAD + Qwen3-ASR 0.6B (sherpa-onnx int8)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .base import SAMPLE_RATE
from .vad import VadSegmentedRecognizer


class Qwen3AsrRecognizer(VadSegmentedRecognizer):
    name = "Qwen3-ASR"

    def __init__(self, model_dir: Path, vad_model: Path, *, hotwords: tuple[str, ...] = (),
                 num_threads: int = 2, min_silence: float = 0.5, max_speech: float = 15.0) -> None:
        import sherpa_onnx

        d = Path(model_dir)
        self._rec = sherpa_onnx.OfflineRecognizer.from_qwen3_asr(
            conv_frontend=str(d / "conv_frontend.onnx"),
            encoder=str(d / "encoder.int8.onnx"),
            decoder=str(d / "decoder.int8.onnx"),
            tokenizer=str(d / "tokenizer"),
            hotwords=",".join(hotwords),
            num_threads=num_threads,
            max_new_tokens=256,
        )
        super().__init__(vad_model, min_silence=min_silence, max_speech=max_speech)

    def _decode(self, samples: np.ndarray) -> str:
        stream = self._rec.create_stream()
        stream.set_option("language", "Korean")
        stream.accept_waveform(SAMPLE_RATE, samples)
        self._rec.decode_stream(stream)
        return stream.result.text
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_asr_vad.py tests/test_asr_engines.py -v`
Expected:
- `test_asr_vad.py`: 1 passed
- SenseVoice·Zipformer 실제 모델 테스트: 모델이 있으면 계속 통과
- Qwen3 테스트 2개: 모델이 있으면 passed, 없으면 skipped

- [ ] **Step 5: 커밋**

```bash
git add src/sukpago/asr tests/test_asr_vad.py tests/test_asr_engines.py
git commit -m "feat: VAD 공통 클래스와 Qwen3-ASR 인식 추가"
```

---

### Task R4: 평가 도구에 2차 후보 등록

**Files:**
- Modify: `tools/evaluate.py`

**Interfaces:**
- Consumes: Task R2와 R3의 클래스, R1의 모델 폴더
- Produces:
  - 음성 인식 후보 `ASR_CANDIDATES = ("zipformer", "sensevoice", "qwen3", "qwen3_hw")`
  - 번역 후보 `MT_CANDIDATES = ("nllb600", "nllb13", "nllb13_pivot", "tsengel13", "tsengel13_pivot", "tgemma", "tgemma_pivot")`
  - 함께 올리는 조합 `COMBOS`: `zipformer`, `qwen3` × `nllb13`, `tsengel13`, `tgemma` = 6개
  - `BUDGET_MB = 3500`

- [ ] **Step 1: 후보 등록부 구현**

`tools/evaluate.py`에서 `ASR_CANDIDATES`부터 `make_mt` 끝까지를 다음으로 바꾼다.

```python
ASR_CANDIDATES = ("zipformer", "sensevoice", "qwen3", "qwen3_hw")
MT_CANDIDATES = ("nllb600", "nllb13", "nllb13_pivot", "tsengel13", "tsengel13_pivot", "tgemma", "tgemma_pivot")
COMBOS = tuple((a, m) for a in ("zipformer", "qwen3") for m in ("nllb13", "tsengel13", "tgemma"))
STEP = SAMPLE_RATE // 10  # 마이크처럼 0.1초씩 넣는다
BUDGET_MB = 3500  # 4GB에서 TTS·화면 몫 약 0.5GB를 뺀 값
EVAL_HOTWORDS = ("NotebookLM", "할루시네이션", "PDF", "YouTube", "Claude", "Gemini")


def make_asr(name: str):
    m = paths.models_dir()
    vad = m / "vad" / "silero_vad.onnx"
    if name == "zipformer":
        from sukpago.asr.zipformer import ZipformerRecognizer
        return ZipformerRecognizer(m / "zipformer-ko")
    if name == "sensevoice":
        from sukpago.asr.sensevoice import SenseVoiceRecognizer
        return SenseVoiceRecognizer(m / "sensevoice", vad)
    from sukpago.asr.qwen3 import Qwen3AsrRecognizer
    return Qwen3AsrRecognizer(m / "qwen3-asr", vad, hotwords=EVAL_HOTWORDS if name == "qwen3_hw" else ())


def make_mt(name: str):
    m = paths.models_dir()
    from sukpago.translate.pivot import PivotTranslator
    if name.startswith("tgemma"):
        from sukpago.translate.gemma import TranslateGemmaTranslator
        engine = TranslateGemmaTranslator(m / "tgemma" / "translategemma-4b-it.Q4_K_M.gguf")
    else:
        from sukpago.translate.nllb import NllbTranslator
        folder = {"nllb600": "nllb-600m", "nllb13": "nllb-1.3b", "tsengel13": "tsengel-1.3b"}
        engine = NllbTranslator(m / folder[name.removesuffix("_pivot")])
    return PivotTranslator(engine, name=name) if name.endswith("_pivot") else engine
```

`main()`의 메모리 측정 반복문을 `COMBOS`로 바꾼다.

```python
    for a, m in COMBOS:
        print(f"메모리 {a} + {m}")
        r = call_worker(["combo", a, m, str(wavs[0]), str(sent_file)])
        if "error" in r:
            lines.append(f"- {a} + {m}: 실행 실패 — {r['error']}")
        else:
            over = " (목표 초과)" if r["peak_mb"] > BUDGET_MB else ""
            lines.append(f"- {a} + {m}: {r['peak_mb']:.0f}MB{over}")
```

번역에 넣을 문장은 계속 Zipformer 결과에서 고른다(`ASR_CANDIDATES`의 첫 번째). Zipformer는 띄어쓰기를 고쳤으니 1차와는 다른 문장이 들어갈 수 있다.

- [ ] **Step 2: 테스트와 커밋**

Run: `uv run pytest -q`
Expected: 전부 통과

```bash
git add tools/evaluate.py
git commit -m "feat: 평가 도구에 2차 후보와 4GB 예산 반영"
```

---

### Task R5: 2차 평가 실행과 엔진 결정

**Files:**
- Modify: `assets/engines.json`, `src/sukpago/engines.py`(선택한 엔진 이름이 `ASR_ENGINES`·`MT_ENGINES`에 없으면 추가), `tests/test_engines.py`, `docs/superpowers/specs/2026-11-24-sukpago-design.md`

- [ ] **Step 1: 평가 실행**

Run: `uv run python tools/evaluate.py`
Expected: `eval_out/report.md` 생성. TranslateGemma가 있어서 1차보다 오래 걸린다.

- [ ] **Step 2: 사용자와 보고서 검토**

설계 문서 4장의 기준으로 검토하고, 메모리 기준은 3500MB를 쓴다. 다음을 정한다.
- 음성 인식 엔진
- 언어별 번역 엔진과 번역 방식(바로 번역 / 영어 경유)
- 고른 조합의 "함께 올렸을 때 최대 메모리"가 3500MB 이하인지

- [ ] **Step 3: 결정 반영**

`assets/engines.json`에 결정을 적는다. 엔진 이름이 새로 생기면 다음도 함께 고친다.
- `engines.py`의 `ASR_ENGINES`와 `MT_ENGINES`
- `test_engines.py`

설계 문서의 다음 부분을 측정값과 결정에 맞게 고친다(이력 표기 없이).
- 1장의 메모리 상한(4GB)
- 3장의 엔진 표와 사실 목록
- 4장의 평가 결과
- 6장의 메모리 예산

```bash
uv run pytest -q
git add assets/engines.json src/sukpago/engines.py tests/test_engines.py docs/superpowers/specs/2026-11-24-sukpago-design.md
git commit -m "docs: 2차 평가 결과로 오프라인 엔진 확정"
```
