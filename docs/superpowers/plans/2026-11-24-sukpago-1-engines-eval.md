# 석파고 계획 1: 엔진과 모델 평가 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 음성 인식·문장 정리·번역 엔진을 화면 없이 동작하는 파이썬 패키지로 만들고, 실제 강의 녹음으로 후보 모델을 평가해 `assets/engines.json`을 정한다.

**Architecture:** `src/sukpago/` 아래에 엔진별 모듈을 프로토콜(`Translator`, `Recognizer`) 뒤에 둔다. 무거운 라이브러리(ctranslate2, llama-cpp-python, sherpa-onnx)는 처음 쓸 때 불러오고, 단위 테스트는 가짜 객체를 주입해 모델 없이 돈다. 실제 모델이 필요한 테스트는 `models/`가 없으면 건너뛴다. 평가는 `tools/evaluate.py`가 엔진마다 하위 프로세스를 띄워 메모리를 따로 잰다.

**Tech Stack:** Python 3.13, uv, pytest, numpy, ctranslate2 4.9.1, sentencepiece 0.2.3, llama-cpp-python 0.3.38, sherpa-onnx 1.13.8, psutil.

**설계 문서:** `docs/superpowers/specs/2026-11-24-sukpago-design.md`

**이 계획의 범위:** 설계 문서 3장(엔진), 4장(평가), 5장의 문장 정리와 반복 방지.
- TTS, 오디오 재생, 마이크, 파이프라인 스레드, 두 창은 **계획 2**에서 다룬다.
- PyInstaller와 GitHub Actions는 **계획 3**에서 다룬다.
- 계획 2와 3은 이 계획의 평가 결과로 엔진이 정해진 뒤에 쓴다.

**설계 문서와 다르게 정한 점** (Task 14에서 설계 문서에 반영)
- **Hy-MT2 중국어 프롬프트:** Tencent README에 따라 한국어→중국어는 중국어 프롬프트에 언어 이름 `中文`을 쓴다. 설계 문서 표의 "Simplified Chinese"는 쓰지 않는다.
- **Hy-MT2 출력 길이 상한:** `입력 토큰 × 3 + 16`으로 정한다. 키릴 몽골어는 같은 뜻이라도 토큰이 많아서 ×2로는 문장이 잘릴 수 있다.
- **Zipformer 핫워드:** kangkyu 모델에는 bpe 모델 파일이 없어서 핫워드 지원이 불확실하다. 이 계획에서는 용어 사전 치환(Glossary)만 구현하고, 핫워드는 계획 2에서 따로 시험한다.
- **Zipformer 청크:** chunk-64(지연 1.28초, KsponSpeech CER 7.53%)를 쓴다. 확정 자막은 말이 끊긴 뒤에 나오므로 이 지연은 문제가 되지 않는다.

## Global Constraints

- 실행 환경은 Windows 10/11 64비트이고, 개발은 macOS에서 한다. OS 전용 기능은 쓰지 않는다.
- Python은 3.13으로 고정한다(`requires-python = ">=3.13,<3.14"`, `.python-version` = `3.13`). 환경은 uv로 관리한다.
- 카드 등록과 API 키가 필요한 서비스는 쓰지 않는다.
- 오프라인으로 전부 켰을 때 최대 메모리는 2GB 이하여야 한다. 그중 음성 인식과 번역을 합친 목표는 1.8GB 이하다.
- `sherpa-onnx==1.13.8`로 고정한다(2.0.x에서는 Piper 영어 모델이 실패했다).
- 몽골어 출력은 키릴 문자(할하 방언)여야 한다. 전통 몽골 문자(U+1800–U+18AF)가 나오면 실패로 본다.
- 모델은 리비전이 고정된 URL에서 받고, 받은 뒤 SHA256으로 검증한다.
- 다음 폴더는 커밋하지 않는다(`.gitignore`에 넣는다).
  - `eval_data/`: 강의 녹음
  - `eval_out/`: 평가 결과(강의 내용이 들어 있음)
  - `models/`: 모델 파일
- 문서에는 변경 이력을 적지 않는다. 이력은 커밋으로 남긴다.
- 커밋 메시지는 한국어로 쓰고 `feat:`, `test:`, `docs:`, `chore:` 접두사를 붙인다.
- 모든 명령은 저장소 루트에서 `uv run ...`으로 실행한다.

## 파일 구조

| 파일 | 역할 |
|---|---|
| `pyproject.toml`, `.python-version` | 패키지, 의존성, pytest 설정 |
| `src/sukpago/languages.py` | 대상 언어와 엔진별 언어 코드 |
| `src/sukpago/paths.py` | `models/`, `assets/` 위치 (exe와 개발 환경 모두) |
| `src/sukpago/text/glossary.py` | 용어 고치기 (띄어쓰기 무시 치환) |
| `src/sukpago/text/assembler.py` | 인식 조각 → 번역할 문장 (군말, 반복, 이어붙이기, 자르기) |
| `src/sukpago/translate/base.py` | `Translator` 프로토콜, 예외 |
| `src/sukpago/translate/mymemory.py` | 온라인 번역 (키 없음) |
| `src/sukpago/translate/nllb.py` | 오프라인 NLLB (CTranslate2) |
| `src/sukpago/translate/hymt.py` | 오프라인 Hy-MT2 (llama-cpp-python) |
| `src/sukpago/translate/router.py` | 온라인 실패 시 오프라인 전환 |
| `src/sukpago/engines.py` | `engines.json` 읽기, 번역 모델은 한 번에 하나만 올리는 `ModelManager` |
| `src/sukpago/asr/base.py` | `Recognizer` 프로토콜, `AsrEvent`, `Framer`, wav 읽기 |
| `src/sukpago/asr/zipformer.py` | 스트리밍 Zipformer (sherpa-onnx) |
| `src/sukpago/asr/sensevoice.py` | VAD + SenseVoice (sherpa-onnx) |
| `src/sukpago/quality.py` | 전통 몽골 문자·반복 검사, 최대 메모리 측정 |
| `assets/engines.json` | 어떤 엔진을 쓸지 |
| `tools/models.lock.json` | 모델 URL, 크기, SHA256 |
| `tools/download_models.py` | 모델 받기와 검증 |
| `tools/evaluate.py` | 강의 녹음으로 후보 비교, `eval_out/report.md` 작성 |
| `tests/…` | 모듈마다 테스트 하나씩 |

---

### Task 1: 프로젝트 뼈대, 언어 표, 경로

**Files:**
- Create: `pyproject.toml`, `.python-version`, `src/sukpago/__init__.py`, `src/sukpago/languages.py`, `src/sukpago/paths.py`, `tests/conftest.py`, `tests/test_languages.py`, `tests/test_paths.py`
- Modify: `.gitignore` (끝에 줄 추가)

**Interfaces:**
- Produces:
  - `sukpago.languages.Language(id, name_ko, mymemory, nllb, hymt_name, edge_voice)`
  - `LANGUAGES: dict[str, Language]`, `TARGET_ORDER = ("mn", "zh", "en")`, `SOURCE_MYMEMORY = "ko"`, `SOURCE_NLLB = "kor_Hang"`, `get(lang_id) -> Language` (모르는 언어는 `KeyError`)
  - `sukpago.paths.app_root() -> Path`, `models_dir() -> Path` (환경 변수 `SUKPAGO_MODELS`가 있으면 그 경로), `assets_dir() -> Path`
  - pytest fixture `model_path(*parts) -> Path` (파일이 없으면 테스트를 건너뜀)

- [ ] **Step 1: 작업 브랜치 만들기**

```bash
git checkout -b feat/engines-eval
```

- [ ] **Step 2: `pyproject.toml`과 `.python-version` 작성**

`pyproject.toml`:

```toml
[project]
name = "sukpago"
version = "0.1.0"
description = "강의를 실시간으로 몽골어·중국어·영어로 번역하는 프로그램"
requires-python = ">=3.13,<3.14"
dependencies = [
  "numpy>=2.1",
  "ctranslate2==4.9.1",
  "sentencepiece==0.2.3",
  "llama-cpp-python==0.3.38",
  "sherpa-onnx==1.13.8",
  "sherpa-onnx-core==1.13.8",
  "psutil>=6.0",
]

[dependency-groups]
dev = ["pytest>=8.3"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/sukpago"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["tools"]
markers = ["models: models/ 폴더의 실제 모델이 필요함 (없으면 건너뜀)"]

[[tool.uv.index]]
name = "llama-cpp-cpu"
url = "https://abetlen.github.io/llama-cpp-python/whl/cpu"
explicit = true

[tool.uv.sources]
llama-cpp-python = [{ index = "llama-cpp-cpu", marker = "sys_platform == 'win32'" }]
```

`.python-version`:

```
3.13
```

- [ ] **Step 3: `.gitignore` 끝에 추가**

```
# 석파고: 모델, 강의 녹음, 평가 결과는 커밋하지 않는다
models/
eval_data/
eval_out/
*.part
```

- [ ] **Step 4: 실패하는 테스트 작성**

`tests/test_languages.py`:

```python
import pytest

from sukpago import languages as L


def test_target_order_is_mn_zh_en():
    assert L.TARGET_ORDER == ("mn", "zh", "en")
    assert set(L.TARGET_ORDER) == set(L.LANGUAGES)


def test_engine_codes():
    assert (L.get("mn").mymemory, L.get("mn").nllb) == ("mn", "khk_Cyrl")
    assert (L.get("zh").mymemory, L.get("zh").nllb) == ("zh-CN", "zho_Hans")
    assert (L.get("en").mymemory, L.get("en").nllb) == ("en", "eng_Latn")
    assert (L.SOURCE_MYMEMORY, L.SOURCE_NLLB) == ("ko", "kor_Hang")


def test_hymt_names():
    assert "Cyrillic" in L.get("mn").hymt_name
    assert L.get("zh").hymt_name == "中文"
    assert L.get("en").hymt_name == "English"


def test_unknown_language_raises():
    with pytest.raises(KeyError, match="지원하지 않는 언어"):
        L.get("ja")
```

`tests/test_paths.py`:

```python
import sys

from sukpago import paths


def test_dev_root_is_repo_root():
    assert (paths.app_root() / "pyproject.toml").exists()


def test_frozen_root_is_exe_folder(monkeypatch, tmp_path):
    monkeypatch.delenv("SUKPAGO_MODELS", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "SukPaGo.exe"))
    assert paths.app_root() == tmp_path.resolve()
    assert paths.models_dir() == tmp_path.resolve() / "models"
    assert paths.assets_dir() == tmp_path.resolve() / "assets"


def test_models_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("SUKPAGO_MODELS", str(tmp_path))
    assert paths.models_dir() == tmp_path
```

`tests/conftest.py`:

```python
import pytest

from sukpago import paths


@pytest.fixture
def model_path():
    """models/ 아래 경로를 돌려준다. 없으면 테스트를 건너뛴다."""

    def _get(*parts: str):
        p = paths.models_dir().joinpath(*parts)
        if not p.exists():
            pytest.skip(f"모델 없음: {p} (uv run python tools/download_models.py 로 받으세요)")
        return p

    return _get
```

`src/sukpago/__init__.py`:

```python
"""석파고(SukPaGo): 강의 실시간 번역기."""
```

- [ ] **Step 5: 의존성 설치 후 테스트가 실패하는지 확인**

Run: `uv sync`
Expected: Python 3.13이 없으면 uv가 받아서 설치하고, 의존성을 설치한다. macOS에서는 llama-cpp-python을 소스에서 빌드하므로 몇 분 걸린다. 빌드가 실패하면 `xcode-select --install`을 실행한 뒤 다시 시도한다.

Run: `uv run pytest tests/test_languages.py tests/test_paths.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'sukpago.languages'`)

- [ ] **Step 6: 구현**

`src/sukpago/languages.py`:

```python
"""번역 대상 언어와 엔진별 언어 코드."""

from __future__ import annotations

from dataclasses import dataclass

SOURCE_MYMEMORY = "ko"
SOURCE_NLLB = "kor_Hang"


@dataclass(frozen=True)
class Language:
    id: str
    name_ko: str
    mymemory: str
    nllb: str
    hymt_name: str
    edge_voice: str


LANGUAGES: dict[str, Language] = {
    "mn": Language("mn", "몽골어", "mn", "khk_Cyrl",
                   "Mongolian (Cyrillic script, as used in Mongolia)", "mn-MN-YesuiNeural"),
    "zh": Language("zh", "중국어", "zh-CN", "zho_Hans", "中文", "zh-CN-XiaoxiaoNeural"),
    "en": Language("en", "영어", "en", "eng_Latn", "English", "en-US-JennyNeural"),
}

TARGET_ORDER: tuple[str, ...] = ("mn", "zh", "en")


def get(lang_id: str) -> Language:
    try:
        return LANGUAGES[lang_id]
    except KeyError:
        raise KeyError(f"지원하지 않는 언어: {lang_id!r}") from None
```

`src/sukpago/paths.py`:

```python
"""모델·에셋 폴더 위치. PyInstaller exe에서는 exe 옆, 개발 중에는 저장소 루트."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def models_dir() -> Path:
    override = os.environ.get("SUKPAGO_MODELS")
    return Path(override) if override else app_root() / "models"


def assets_dir() -> Path:
    return app_root() / "assets"
```

- [ ] **Step 7: 테스트 통과 확인**

Run: `uv run pytest -v`
Expected: 7 passed

- [ ] **Step 8: 커밋**

```bash
git add pyproject.toml uv.lock .python-version .gitignore src tests
git commit -m "chore: uv 프로젝트 뼈대와 언어 표, 경로 추가"
```

---

### Task 2: 용어 고치기 (Glossary)

**Files:**
- Create: `src/sukpago/text/__init__.py` (빈 파일), `src/sukpago/text/glossary.py`, `tests/test_glossary.py`

**Interfaces:**
- Produces:
  - `sukpago.text.glossary.Rule(wrong: str, right: str)`
  - `Glossary(rules: list[Rule] | None = None)`
  - 메서드: `.rules -> list[Rule]`, `.add(wrong, right)` (같은 `wrong`이 있으면 교체, 빈 값이면 `ValueError`), `.remove(wrong)`, `.apply(text) -> str`, `.to_json() -> list[dict]`, `Glossary.from_json(data)`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_glossary.py`:

```python
import pytest

from sukpago.text.glossary import Glossary, Rule


def test_replaces_regardless_of_spacing():
    g = Glossary([Rule("노트북 에램", "NotebookLM")])
    assert g.apply("노트북에램 써 보셨나요") == "NotebookLM 써 보셨나요"
    assert g.apply("노트북  에램 이라는") == "NotebookLM 이라는"


def test_longest_rule_wins():
    g = Glossary([Rule("노트북", "랩톱"), Rule("노트북 에램", "NotebookLM")])
    assert g.apply("노트북 에램과 노트북") == "NotebookLM과 랩톱"


def test_add_replaces_same_wrong_and_remove():
    g = Glossary()
    g.add("한강 리스크", "할루시네이션")
    g.add("한강 리스크", "할루시네이션 리스크")
    assert g.rules == [Rule("한강 리스크", "할루시네이션 리스크")]
    g.remove("한강 리스크")
    assert g.apply("한강 리스크") == "한강 리스크"


def test_empty_rule_rejected():
    with pytest.raises(ValueError):
        Glossary().add(" ", "x")


def test_special_characters_are_literal():
    g = Glossary([Rule("C++", "씨플플")])
    assert g.apply("C++ 수업") == "씨플플 수업"


def test_json_roundtrip():
    g = Glossary([Rule("a b", "AB")])
    assert Glossary.from_json(g.to_json()).rules == g.rules
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `uv run pytest tests/test_glossary.py -v`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: 구현**

`src/sukpago/text/glossary.py`:

```python
"""용어 고치기: 잘못 인식된 말을 바른 말로 바꾼다. 띄어쓰기 차이는 무시한다."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    wrong: str
    right: str


def _pattern(wrong: str) -> re.Pattern[str]:
    chars = [re.escape(c) for c in wrong if not c.isspace()]
    return re.compile(r"\s*".join(chars))


class Glossary:
    def __init__(self, rules: list[Rule] | None = None) -> None:
        self._rules: list[Rule] = []
        self._compiled: list[tuple[re.Pattern[str], str]] = []
        for r in rules or []:
            self.add(r.wrong, r.right)

    @property
    def rules(self) -> list[Rule]:
        return list(self._rules)

    def add(self, wrong: str, right: str) -> None:
        wrong, right = wrong.strip(), right.strip()
        if not wrong or not right:
            raise ValueError("인식된 말과 바꿀 말은 비어 있으면 안 됩니다")
        self._rules = [r for r in self._rules if r.wrong != wrong] + [Rule(wrong, right)]
        self._compile()

    def remove(self, wrong: str) -> None:
        self._rules = [r for r in self._rules if r.wrong != wrong.strip()]
        self._compile()

    def apply(self, text: str) -> str:
        for pat, right in self._compiled:
            text = pat.sub(lambda _m, r=right: r, text)
        return text

    def to_json(self) -> list[dict[str, str]]:
        return [{"wrong": r.wrong, "right": r.right} for r in self._rules]

    @classmethod
    def from_json(cls, data: list[dict[str, str]]) -> "Glossary":
        return cls([Rule(d["wrong"], d["right"]) for d in data])

    def _compile(self) -> None:
        ordered = sorted(self._rules, key=lambda r: len(re.sub(r"\s", "", r.wrong)), reverse=True)
        self._compiled = [(_pattern(r.wrong), r.right) for r in ordered]
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_glossary.py -v`
Expected: 6 passed

- [ ] **Step 5: 커밋**

```bash
git add src/sukpago/text tests/test_glossary.py
git commit -m "feat: 용어 고치기(Glossary) 추가"
```

---

### Task 3: 문장 정리 (SentenceAssembler)

**Files:**
- Create: `src/sukpago/text/assembler.py`, `tests/test_assembler.py`

**Interfaces:**
- Consumes: `Glossary` (Task 2)
- Produces:
  - `sukpago.text.assembler.SentenceAssembler(glossary: Glossary | None = None, *, min_chars=8, max_chars=120, wait_s=3.0)`
  - `.feed(text: str, now: float) -> list[str]`: 확정된 인식 조각 하나를 넣고, 번역할 문장 목록을 받는다.
  - `.tick(now: float) -> list[str]`: 기다리던 짧은 조각이 `wait_s`를 넘기면 내보낸다.
  - `.flush() -> list[str]`
  - `.clean(text) -> str`: 군말과 반복만 정리한다.
  - 상수 `FILLERS`, `LEADING_FILLERS`

규칙:
- 공백을 정리한다.
- 바로 이어지는 같은 단어는 하나로 줄인다("많이 많이" → "많이").
- 말 더듬기를 정리한다("여러분러분" → "여러분"). 단, "반짝반짝" 같은 첩어는 그대로 둔다.
- 조각 전체가 군말이면 버린다.
- 앞뒤의 감탄사("어", "음", "아", "에", "응")는 지운다. "그"는 관형사일 수 있어서 앞에서 지우지 않는다.
- 용어 사전을 적용한다.
- 띄어쓰기를 뺀 길이가 8자 미만이면 다음 조각과 이어 붙인다. 최대 3초 기다린다.
- 120자를 넘으면 문장 끝(`.?!` 뒤, 또는 `요/다/죠/까` 뒤의 공백)에서 잘라 120자 이하로 묶는다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_assembler.py`:

```python
from sukpago.text.assembler import SentenceAssembler
from sukpago.text.glossary import Glossary, Rule


def test_filler_only_segment_is_dropped():
    a = SentenceAssembler()
    assert a.feed("어.", 0) == []
    assert a.feed("네 네", 1) == []
    assert a.flush() == []


def test_leading_and_trailing_fillers_removed_but_determiner_kept():
    a = SentenceAssembler()
    assert a.feed("음 오늘은 광합성을 배울 거예요 어", 0) == ["오늘은 광합성을 배울 거예요"]
    assert a.feed("그 사람은 과학자였습니다", 1) == ["그 사람은 과학자였습니다"]


def test_stutter_and_repeated_words_collapsed():
    assert SentenceAssembler().clean("여러분러분 많이 많이 들어 보셨죠") == "여러분 많이 들어 보셨죠"


def test_reduplicated_words_are_kept():
    text = "별이 반짝반짝 하나하나 빛나요"
    assert SentenceAssembler().clean(text) == text


def test_short_fragment_waits_for_next():
    a = SentenceAssembler()
    assert a.feed("교과서", 0.0) == []
    assert a.feed("사십오 쪽 펴 주세요", 1.0) == ["교과서 사십오 쪽 펴 주세요"]


def test_short_fragment_flushed_after_wait():
    a = SentenceAssembler(wait_s=3.0)
    assert a.feed("그렇구나", 10.0) == []
    assert a.tick(12.0) == []
    assert a.tick(13.0) == ["그렇구나"]
    assert a.tick(20.0) == []


def test_long_text_split_at_endings_within_limit():
    a = SentenceAssembler(max_chars=40)
    text = ("오늘은 광합성에 대해 배울 거예요 식물은 햇빛과 물을 이용해서 양분을 만들어요 "
            "다음 주까지 숙제를 내세요")
    out = a.feed(text, 0)
    assert out == [
        "오늘은 광합성에 대해 배울 거예요",
        "식물은 햇빛과 물을 이용해서 양분을 만들어요 다음 주까지 숙제를 내세요",
    ]
    assert all(len(s) <= 40 for s in out)


def test_very_long_piece_without_endings_is_wrapped_at_spaces():
    a = SentenceAssembler(max_chars=20)
    text = "가나다 라마바 사아자 차카타 파하가 나다라 마바사"
    out = a.feed(text, 0)
    assert all(len(s) <= 20 for s in out)
    assert " ".join(out) == text


def test_glossary_applied():
    a = SentenceAssembler(Glossary([Rule("노트북 에램", "NotebookLM")]))
    assert a.feed("노트북 에램 이라는 사이트가 있어요", 0) == ["NotebookLM 이라는 사이트가 있어요"]
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `uv run pytest tests/test_assembler.py -v`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: 구현**

`src/sukpago/text/assembler.py`:

```python
"""음성 인식 조각을 번역하기 좋은 문장으로 정리한다."""

from __future__ import annotations

import re

from .glossary import Glossary

FILLERS = frozenset({"어", "음", "그", "네", "아", "예", "에", "저", "뭐", "자", "응"})
LEADING_FILLERS = frozenset({"어", "음", "아", "에", "응"})
_PUNCT = ".,?!。，？！…~"
_REPEATED_WORD = re.compile(r"(?<!\S)(\S+)(?:\s+\1)+(?!\S)")
_STUTTER = re.compile(r"(\S+?)(\S{2,})\2")
_SPLIT = re.compile(r"(?<=[.?!。？！])\s+|(?<=[요다죠까])\s+")


def _bare(token: str) -> str:
    return token.strip(_PUNCT)


def _nospace_len(s: str) -> int:
    return len(re.sub(r"\s", "", s))


class SentenceAssembler:
    def __init__(self, glossary: Glossary | None = None, *, min_chars: int = 8,
                 max_chars: int = 120, wait_s: float = 3.0) -> None:
        self.glossary = glossary or Glossary()
        self.min_chars = min_chars
        self.max_chars = max_chars
        self.wait_s = wait_s
        self._pending: str | None = None
        self._since = 0.0

    def feed(self, text: str, now: float) -> list[str]:
        cleaned = self.clean(text)
        if not cleaned:
            return []
        if self._pending is not None:
            cleaned = f"{self._pending} {cleaned}"
        else:
            self._since = now
        self._pending = None
        if _nospace_len(cleaned) < self.min_chars:
            self._pending = cleaned
            return []
        return self._split(cleaned)

    def tick(self, now: float) -> list[str]:
        if self._pending is not None and now - self._since >= self.wait_s:
            return self.flush()
        return []

    def flush(self) -> list[str]:
        if self._pending is None:
            return []
        text, self._pending = self._pending, None
        return self._split(text)

    def clean(self, text: str) -> str:
        t = re.sub(r"\s+", " ", text).strip()
        t = _REPEATED_WORD.sub(r"\1", t)
        t = _STUTTER.sub(r"\1\2", t)
        tokens = t.split(" ") if t else []
        if all(not _bare(tok) or _bare(tok) in FILLERS for tok in tokens):
            return ""
        while tokens and _bare(tokens[0]) in LEADING_FILLERS:
            tokens.pop(0)
        while tokens and _bare(tokens[-1]) in LEADING_FILLERS:
            tokens.pop()
        return self.glossary.apply(" ".join(tokens)).strip()

    def _split(self, text: str) -> list[str]:
        if len(text) <= self.max_chars:
            return [text]
        out: list[str] = []
        cur = ""
        for piece in (p for p in _SPLIT.split(text) if p):
            for part in self._wrap(piece):
                if cur and len(cur) + 1 + len(part) > self.max_chars:
                    out.append(cur)
                    cur = part
                else:
                    cur = f"{cur} {part}" if cur else part
        if cur:
            out.append(cur)
        return out

    def _wrap(self, s: str) -> list[str]:
        parts: list[str] = []
        while len(s) > self.max_chars:
            cut = s.rfind(" ", 0, self.max_chars + 1)
            if cut <= 0:
                cut = self.max_chars
            parts.append(s[:cut].strip())
            s = s[cut:].strip()
        if s:
            parts.append(s)
        return parts
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_assembler.py -v`
Expected: 9 passed

- [ ] **Step 5: 커밋**

```bash
git add src/sukpago/text/assembler.py tests/test_assembler.py
git commit -m "feat: 인식 조각을 문장으로 정리하는 SentenceAssembler 추가"
```

---

### Task 4: 번역 인터페이스와 MyMemory 온라인 번역

**Files:**
- Create: `src/sukpago/translate/__init__.py` (빈 파일), `src/sukpago/translate/base.py`, `src/sukpago/translate/mymemory.py`, `tests/test_mymemory.py`

**Interfaces:**
- Consumes: `languages.get`, `SOURCE_MYMEMORY` (Task 1)
- Produces:
  - 예외: `TranslateError(Exception)`, `QuotaExceeded(TranslateError)`
  - 프로토콜: `Translator` (속성 `name: str`, 메서드 `translate(text: str, lang: str) -> str`), `Unloadable` (`unload() -> None`)
  - `MyMemoryTranslator(email: str | None = None, timeout: float = 5.0, fetch: Fetch | None = None)`
    - `Fetch = Callable[[str, float], tuple[int, bytes]]`: URL과 타임아웃을 받아 `(HTTP 상태, 본문)`을 돌려준다.
    - `name = "MyMemory"`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_mymemory.py`:

```python
import json
from urllib.parse import parse_qs, urlparse

import pytest

from sukpago.translate.base import QuotaExceeded, TranslateError
from sukpago.translate.mymemory import MyMemoryTranslator

OK = {"responseStatus": 200, "quotaFinished": False,
      "responseData": {"translatedText": "Анхаарлаа төвлөрүүл."}}


def fake(status=200, payload=None, raw=None):
    calls = []

    def fetch(url, timeout):
        calls.append((url, timeout))
        return status, (raw if raw is not None else json.dumps(payload).encode())

    return fetch, calls


def query(calls):
    return parse_qs(urlparse(calls[0][0]).query)


def test_builds_query_and_parses():
    fetch, calls = fake(payload=OK)
    assert MyMemoryTranslator(fetch=fetch).translate("집중하세요.", "mn") == "Анхаарлаа төвлөрүүл."
    q = query(calls)
    assert q["q"] == ["집중하세요."] and q["langpair"] == ["ko|mn"] and "de" not in q
    assert calls[0][1] == 5.0


def test_email_and_chinese_code():
    fetch, calls = fake(payload=OK)
    MyMemoryTranslator(email="me@example.com", fetch=fetch).translate("x", "zh")
    q = query(calls)
    assert q["langpair"] == ["ko|zh-CN"] and q["de"] == ["me@example.com"]


def test_html_entities_unescaped():
    fetch, _ = fake(payload={**OK, "responseData": {"translatedText": "let&#39;s go"}})
    assert MyMemoryTranslator(fetch=fetch).translate("x", "en") == "let's go"


@pytest.mark.parametrize("status,payload", [
    (200, {**OK, "quotaFinished": True}),
    (200, {"responseStatus": 429, "responseData": {
        "translatedText": "MYMEMORY WARNING: YOU USED ALL AVAILABLE FREE TRANSLATIONS FOR TODAY."}}),
    (429, {}),
])
def test_quota(status, payload):
    fetch, _ = fake(status=status, payload=payload)
    with pytest.raises(QuotaExceeded):
        MyMemoryTranslator(fetch=fetch).translate("x", "en")


@pytest.mark.parametrize("status,raw", [
    (500, b"oops"),
    (200, b"not json"),
    (200, json.dumps({"responseStatus": "403",
                      "responseData": {"translatedText": "INVALID LANGUAGE PAIR"}}).encode()),
    (200, json.dumps({"responseStatus": 200, "responseData": {"translatedText": "  "}}).encode()),
])
def test_errors(status, raw):
    fetch, _ = fake(status=status, raw=raw)
    with pytest.raises(TranslateError) as e:
        MyMemoryTranslator(fetch=fetch).translate("x", "en")
    assert not isinstance(e.value, QuotaExceeded)
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `uv run pytest tests/test_mymemory.py -v`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: 구현**

`src/sukpago/translate/base.py`:

```python
"""번역 엔진 공통 인터페이스."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class TranslateError(Exception):
    """번역 실패. 라우터는 이 예외를 보고 오프라인으로 넘어간다."""


class QuotaExceeded(TranslateError):
    """온라인 무료 한도를 다 썼다."""


@runtime_checkable
class Translator(Protocol):
    name: str

    def translate(self, text: str, lang: str) -> str: ...


@runtime_checkable
class Unloadable(Protocol):
    def unload(self) -> None: ...
```

`src/sukpago/translate/mymemory.py`:

```python
"""MyMemory 온라인 번역. API 키가 필요 없다(이메일을 주면 하루 한도가 늘어남)."""

from __future__ import annotations

import html
import json
import urllib.error
import urllib.request
from typing import Callable
from urllib.parse import urlencode

from ..languages import SOURCE_MYMEMORY, get
from .base import QuotaExceeded, TranslateError

Fetch = Callable[[str, float], tuple[int, bytes]]
ENDPOINT = "https://api.mymemory.translated.net/get"


def _urllib_fetch(url: str, timeout: float) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": "SukPaGo/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise TranslateError(f"네트워크 오류: {e}") from e


class MyMemoryTranslator:
    name = "MyMemory"

    def __init__(self, email: str | None = None, timeout: float = 5.0,
                 fetch: Fetch | None = None) -> None:
        self.email = email
        self.timeout = timeout
        self._fetch = fetch or _urllib_fetch

    def translate(self, text: str, lang: str) -> str:
        params = {"q": text, "langpair": f"{SOURCE_MYMEMORY}|{get(lang).mymemory}"}
        if self.email:
            params["de"] = self.email
        status, body = self._fetch(f"{ENDPOINT}?{urlencode(params)}", self.timeout)
        if status == 429:
            raise QuotaExceeded("MyMemory 하루 한도를 넘었습니다")
        if status != 200:
            raise TranslateError(f"MyMemory HTTP {status}")
        try:
            data = json.loads(body)
        except ValueError as e:
            raise TranslateError("MyMemory 응답을 읽을 수 없습니다") from e
        out = (data.get("responseData") or {}).get("translatedText") or ""
        if data.get("quotaFinished") or "MYMEMORY WARNING" in out.upper():
            raise QuotaExceeded("MyMemory 하루 한도를 넘었습니다")
        try:
            code = int(data.get("responseStatus", 0))
        except (TypeError, ValueError):
            code = 0
        if code != 200:
            raise TranslateError(f"MyMemory 상태 {code}: {out}")
        out = html.unescape(out).strip()
        if not out:
            raise TranslateError("MyMemory가 빈 번역을 돌려주었습니다")
        return out
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_mymemory.py -v`
Expected: 10 passed

- [ ] **Step 5: 커밋**

```bash
git add src/sukpago/translate tests/test_mymemory.py
git commit -m "feat: 번역 인터페이스와 MyMemory 온라인 번역 추가"
```

---

### Task 5: 오프라인 번역 NLLB (CTranslate2)

**Files:**
- Create: `src/sukpago/translate/nllb.py`, `tests/test_nllb.py`

**Interfaces:**
- Consumes: `TranslateError` (Task 4), `languages.get`, `SOURCE_NLLB`
- Produces:
  - `NllbTranslator(model_dir: Path, *, intra_threads: int = 4, beam_size: int = 2, loader=None)`
    - `loader(model_dir, intra_threads) -> (sentencepiece 객체, ctranslate2.Translator)`
    - 메서드: `.translate(text, lang) -> str`, `.unload()`, 속성 `.loaded: bool`, `name = "NLLB-600M"`
  - 모델 폴더: `models/nllb-600m/` (`model.bin`, `config.json`, `shared_vocabulary.txt`, `sentencepiece.bpe.model`)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_nllb.py`:

```python
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
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `uv run pytest tests/test_nllb.py -v`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: 구현**

`src/sukpago/translate/nllb.py`:

```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_nllb.py -v`
Expected: 3 passed, 1 skipped (모델은 Task 12에서 받는다)

- [ ] **Step 5: 커밋**

```bash
git add src/sukpago/translate/nllb.py tests/test_nllb.py
git commit -m "feat: NLLB 오프라인 번역 추가"
```

---

### Task 6: 오프라인 번역 Hy-MT2 (llama-cpp-python)

**Files:**
- Create: `src/sukpago/translate/hymt.py`, `tests/test_hymt.py`

**Interfaces:**
- Consumes: `TranslateError` (Task 4), `languages.get`
- Produces:
  - `build_prompt(text: str, lang: str) -> str`
  - `clean_output(s: str) -> str`
  - `HyMtTranslator(model_path: Path, *, n_ctx: int = 1024, n_threads: int = 4, loader=None)`
    - `loader(model_path, n_ctx, n_threads) -> llama_cpp.Llama 객체`
    - 메서드: `.translate()`, `.unload()`, 속성 `.loaded`, `name = "Hy-MT2-1.8B"`
  - 모델 파일: `models/hymt2/Hy-MT2-1.8B-Q4_K_M.gguf`. GGUF 안에 Hunyuan 채팅 템플릿이 들어 있어서 `create_chat_completion`이 그대로 동작한다(2026-11-24에 헤더를 직접 확인함).

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_hymt.py`:

```python
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
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `uv run pytest tests/test_hymt.py -v`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: 구현**

`src/sukpago/translate/hymt.py`:

```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_hymt.py -v`
Expected: 5 passed, 1 skipped

- [ ] **Step 5: 커밋**

```bash
git add src/sukpago/translate/hymt.py tests/test_hymt.py
git commit -m "feat: Hy-MT2 오프라인 번역 추가"
```

---

### Task 7: 엔진 설정과 번역 모델 관리 (engines.py)

**Files:**
- Create: `src/sukpago/engines.py`, `assets/engines.json`, `tests/test_engines.py`

**Interfaces:**
- Consumes: `TARGET_ORDER` (Task 1), `Translator`, `Unloadable` (Task 4)
- Produces:
  - `EngineConfig(asr: str, offline_mt: dict[str, str])`
  - `ASR_ENGINES = ("zipformer", "sensevoice")`, `MT_ENGINES = ("hymt", "nllb")`
  - `parse_engines(data: dict) -> EngineConfig` (잘못된 값이면 `ValueError`), `load_engines(path: Path) -> EngineConfig`
  - `ModelManager(factories: dict[str, Callable[[], Translator]])`: `.get(name) -> Translator`, `.unload()`, `.active_name`
    - 다른 이름을 요청하면 이전 엔진을 `unload()`하고 새로 만든다.
    - 모르는 이름은 `KeyError`.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_engines.py`:

```python
import json

import pytest

from sukpago import paths
from sukpago.engines import ModelManager, load_engines, parse_engines

VALID = {"asr": "zipformer", "offline_mt": {"mn": "hymt", "zh": "hymt", "en": "nllb"}}


def test_parse_valid():
    cfg = parse_engines(VALID)
    assert cfg.asr == "zipformer"
    assert cfg.offline_mt == {"mn": "hymt", "zh": "hymt", "en": "nllb"}


@pytest.mark.parametrize("data,msg", [
    ({**VALID, "asr": "whisper"}, "asr"),
    ({"asr": "zipformer", "offline_mt": {"mn": "hymt", "zh": "hymt"}}, "빠졌습니다"),
    ({"asr": "zipformer", "offline_mt": {"mn": "gpt", "zh": "hymt", "en": "hymt"}}, "알 수 없는"),
])
def test_parse_invalid(data, msg):
    with pytest.raises(ValueError, match=msg):
        parse_engines(data)


def test_repo_engines_json_is_valid():
    load_engines(paths.assets_dir() / "engines.json")


def test_load_from_file(tmp_path):
    p = tmp_path / "engines.json"
    p.write_text(json.dumps(VALID), encoding="utf-8")
    assert load_engines(p).offline_mt["en"] == "nllb"


class FakeEngine:
    def __init__(self, name, log):
        self.name, self.log = name, log
        log.append(f"make {name}")

    def translate(self, text, lang):
        return f"{self.name}:{text}"

    def unload(self):
        self.log.append(f"unload {self.name}")


def test_model_manager_keeps_one_loaded():
    log = []
    mm = ModelManager({"hymt": lambda: FakeEngine("hymt", log), "nllb": lambda: FakeEngine("nllb", log)})
    a = mm.get("hymt")
    assert mm.get("hymt") is a
    mm.get("nllb")
    assert log == ["make hymt", "unload hymt", "make nllb"]
    assert mm.active_name == "nllb"
    mm.unload()
    assert log[-1] == "unload nllb" and mm.active_name is None


def test_model_manager_unknown():
    with pytest.raises(KeyError):
        ModelManager({}).get("hymt")
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `uv run pytest tests/test_engines.py -v`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: 구현**

`assets/engines.json`은 평가 전의 1순위 후보로 시작한다. 평가 결과는 Task 14에서 반영한다.

```json
{
  "asr": "zipformer",
  "offline_mt": {"mn": "hymt", "zh": "hymt", "en": "hymt"}
}
```

`src/sukpago/engines.py`:

```python
"""어떤 엔진을 쓸지(engines.json)와, 오프라인 번역 모델을 한 번에 하나만 올리는 관리자."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .languages import TARGET_ORDER
from .translate.base import Translator, Unloadable

ASR_ENGINES = ("zipformer", "sensevoice")
MT_ENGINES = ("hymt", "nllb")


@dataclass(frozen=True)
class EngineConfig:
    asr: str
    offline_mt: dict[str, str]


def parse_engines(data: dict) -> EngineConfig:
    asr = data.get("asr")
    if asr not in ASR_ENGINES:
        raise ValueError(f"asr는 {ASR_ENGINES} 중 하나여야 합니다: {asr!r}")
    mt = data.get("offline_mt") or {}
    missing = [lang for lang in TARGET_ORDER if lang not in mt]
    if missing:
        raise ValueError(f"offline_mt에 언어가 빠졌습니다: {missing}")
    bad = {lang: eng for lang, eng in mt.items() if eng not in MT_ENGINES}
    if bad:
        raise ValueError(f"알 수 없는 번역 엔진: {bad}")
    return EngineConfig(asr=asr, offline_mt={lang: mt[lang] for lang in TARGET_ORDER})


def load_engines(path: Path) -> EngineConfig:
    return parse_engines(json.loads(Path(path).read_text(encoding="utf-8")))


class ModelManager:
    """오프라인 번역 엔진은 메모리 때문에 한 번에 하나만 올린다."""

    def __init__(self, factories: dict[str, Callable[[], Translator]]) -> None:
        self._factories = dict(factories)
        self._active_name: str | None = None
        self._active: Translator | None = None

    @property
    def active_name(self) -> str | None:
        return self._active_name

    def get(self, name: str) -> Translator:
        if name not in self._factories:
            raise KeyError(f"등록되지 않은 번역 엔진: {name!r}")
        if self._active_name != name or self._active is None:
            self.unload()
            self._active = self._factories[name]()
            self._active_name = name
        return self._active

    def unload(self) -> None:
        if isinstance(self._active, Unloadable):
            self._active.unload()
        self._active = None
        self._active_name = None
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_engines.py -v`
Expected: 8 passed

- [ ] **Step 5: 커밋**

```bash
git add src/sukpago/engines.py assets/engines.json tests/test_engines.py
git commit -m "feat: 엔진 설정과 번역 모델 관리자 추가"
```

---

### Task 8: 번역 라우터 (온라인 실패 시 오프라인 전환)

**Files:**
- Create: `src/sukpago/translate/router.py`, `tests/test_router.py`

**Interfaces:**
- Consumes: `Translator`, `TranslateError` (Task 4), `ModelManager` (Task 7)
- Produces:
  - `RouteResult(text: str, engine: str, fell_back: bool)`
  - `TranslateRouter(online: Translator | None, models: ModelManager, offline_for: dict[str, str])`
  - `.translate(text, lang, *, online: bool) -> RouteResult`
    - `fell_back`은 온라인을 요청했는데 실패해서 오프라인으로 처리했을 때만 `True`다.
    - 오프라인 엔진의 `TranslateError`는 그대로 올라간다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_router.py`:

```python
import pytest

from sukpago.engines import ModelManager
from sukpago.translate.base import QuotaExceeded, TranslateError
from sukpago.translate.router import RouteResult, TranslateRouter


class Eng:
    def __init__(self, name, fail=None):
        self.name, self.fail, self.calls = name, fail, []

    def translate(self, text, lang):
        self.calls.append((text, lang))
        if self.fail:
            raise self.fail
        return f"{self.name}:{lang}:{text}"


def router(online, offline_engines):
    mm = ModelManager({name: (lambda e=e: e) for name, e in offline_engines.items()})
    return TranslateRouter(online, mm, {"mn": "nllb", "zh": "hymt", "en": "hymt"})


def test_online_success():
    r = router(Eng("MyMemory"), {"hymt": Eng("Hy"), "nllb": Eng("NL")})
    assert r.translate("안녕", "zh", online=True) == RouteResult("MyMemory:zh:안녕", "MyMemory", False)


@pytest.mark.parametrize("err", [TranslateError("down"), QuotaExceeded("quota")])
def test_online_failure_falls_back(err):
    r = router(Eng("MyMemory", fail=err), {"hymt": Eng("Hy"), "nllb": Eng("NL")})
    assert r.translate("안녕", "mn", online=True) == RouteResult("NL:mn:안녕", "NL", True)


def test_offline_mode_uses_per_language_engine():
    online = Eng("MyMemory")
    r = router(online, {"hymt": Eng("Hy"), "nllb": Eng("NL")})
    assert r.translate("안녕", "en", online=False) == RouteResult("Hy:en:안녕", "Hy", False)
    assert online.calls == []


def test_no_online_engine_means_offline():
    r = router(None, {"hymt": Eng("Hy"), "nllb": Eng("NL")})
    assert r.translate("안녕", "zh", online=True).fell_back is False


def test_offline_failure_propagates():
    r = router(Eng("MyMemory", fail=TranslateError("x")),
               {"hymt": Eng("Hy", fail=TranslateError("y")), "nllb": Eng("NL")})
    with pytest.raises(TranslateError, match="y"):
        r.translate("안녕", "zh", online=True)
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `uv run pytest tests/test_router.py -v`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: 구현**

`src/sukpago/translate/router.py`:

```python
"""온라인/오프라인 번역 선택. 온라인이 실패하면 그 요청만 오프라인으로 처리한다."""

from __future__ import annotations

from dataclasses import dataclass

from ..engines import ModelManager
from .base import TranslateError, Translator


@dataclass(frozen=True)
class RouteResult:
    text: str
    engine: str
    fell_back: bool


class TranslateRouter:
    def __init__(self, online: Translator | None, models: ModelManager,
                 offline_for: dict[str, str]) -> None:
        self._online = online
        self._models = models
        self._offline_for = dict(offline_for)

    def translate(self, text: str, lang: str, *, online: bool) -> RouteResult:
        fell_back = False
        if online and self._online is not None:
            try:
                return RouteResult(self._online.translate(text, lang), self._online.name, False)
            except TranslateError:
                fell_back = True
        engine = self._models.get(self._offline_for[lang])
        return RouteResult(engine.translate(text, lang), engine.name, fell_back)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_router.py -v`
Expected: 6 passed

- [ ] **Step 5: 커밋**

```bash
git add src/sukpago/translate/router.py tests/test_router.py
git commit -m "feat: 온라인 실패 시 오프라인으로 넘기는 번역 라우터 추가"
```

---

### Task 9: 음성 인식 공통 부분 (AsrEvent, Framer, wav 읽기)

**Files:**
- Create: `src/sukpago/asr/__init__.py` (빈 파일), `src/sukpago/asr/base.py`, `tests/test_asr_base.py`

**Interfaces:**
- Produces:
  - `SAMPLE_RATE = 16000`
  - `AsrEvent(kind: Literal["partial", "final"], text: str, t: float)`: `t`는 지금까지 넣은 오디오의 초
  - 프로토콜 `Recognizer`: `name: str`, `accept(samples: np.ndarray) -> list[AsrEvent]`, `finish() -> list[AsrEvent]`
  - `Framer(size: int)`: `.push(samples) -> list[np.ndarray]`(모두 길이 `size`, float32), `.rest() -> np.ndarray`
  - `load_wav_16k_mono(path: Path) -> np.ndarray` (float32, −1~1). 16kHz 모노 16비트가 아니면 `ValueError`.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_asr_base.py`:

```python
import wave

import numpy as np
import pytest

from sukpago.asr.base import Framer, load_wav_16k_mono


def test_framer_keeps_remainder():
    f = Framer(4)
    out = f.push(np.arange(6, dtype=np.float32))
    assert [x.tolist() for x in out] == [[0, 1, 2, 3]]
    out = f.push(np.arange(6, 9, dtype=np.float32))
    assert [x.tolist() for x in out] == [[4, 5, 6, 7]]
    assert f.rest().tolist() == [8]
    assert f.rest().tolist() == []
    assert out[0].dtype == np.float32


def write_wav(path, rate=16000, channels=1, frames=None):
    frames = frames if frames is not None else np.array([0, 16384, -16384], dtype=np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(np.repeat(frames, channels).tobytes())


def test_load_wav(tmp_path):
    p = tmp_path / "a.wav"
    write_wav(p)
    x = load_wav_16k_mono(p)
    assert x.dtype == np.float32
    assert x.tolist() == [0.0, 0.5, -0.5]


@pytest.mark.parametrize("rate,channels", [(44100, 1), (16000, 2)])
def test_load_wav_rejects_wrong_format(tmp_path, rate, channels):
    p = tmp_path / "b.wav"
    write_wav(p, rate=rate, channels=channels)
    with pytest.raises(ValueError, match="16kHz"):
        load_wav_16k_mono(p)
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `uv run pytest tests/test_asr_base.py -v`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: 구현**

`src/sukpago/asr/base.py`:

```python
"""음성 인식 공통 부분."""

from __future__ import annotations

import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

import numpy as np

SAMPLE_RATE = 16000


@dataclass(frozen=True)
class AsrEvent:
    kind: Literal["partial", "final"]
    text: str
    t: float


class Recognizer(Protocol):
    name: str

    def accept(self, samples: np.ndarray) -> list[AsrEvent]: ...

    def finish(self) -> list[AsrEvent]: ...


class Framer:
    """임의 길이로 들어오는 샘플을 고정 크기 창으로 자른다. 남는 샘플은 다음 호출로 넘긴다."""

    def __init__(self, size: int) -> None:
        self.size = size
        self._buf = np.zeros(0, dtype=np.float32)

    def push(self, samples: np.ndarray) -> list[np.ndarray]:
        self._buf = np.concatenate([self._buf, np.asarray(samples, dtype=np.float32)])
        n = len(self._buf) // self.size * self.size
        frames = [self._buf[i:i + self.size] for i in range(0, n, self.size)]
        self._buf = self._buf[n:]
        return frames

    def rest(self) -> np.ndarray:
        rest, self._buf = self._buf, np.zeros(0, dtype=np.float32)
        return rest


def load_wav_16k_mono(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        if (w.getframerate(), w.getnchannels(), w.getsampwidth()) != (SAMPLE_RATE, 1, 2):
            raise ValueError(f"{path}: 16kHz 모노 16비트 wav만 읽을 수 있습니다")
        data = w.readframes(w.getnframes())
    return np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_asr_base.py -v`
Expected: 4 passed

- [ ] **Step 5: 커밋**

```bash
git add src/sukpago/asr tests/test_asr_base.py
git commit -m "feat: 음성 인식 공통 부분(AsrEvent, Framer, wav 읽기) 추가"
```

---

### Task 10: 음성 인식 엔진 Zipformer와 SenseVoice

**Files:**
- Create: `src/sukpago/asr/zipformer.py`, `src/sukpago/asr/sensevoice.py`, `tests/test_asr_engines.py`

**Interfaces:**
- Consumes: `SAMPLE_RATE`, `AsrEvent`, `Framer` (Task 9)
- Produces:
  - `ZipformerRecognizer(model_dir: Path, *, chunk: int = 64, num_threads: int = 2)`, `name = "Zipformer"`
    - 모델 폴더 `models/zipformer-ko/`: `encoder|decoder|joiner-epoch-99-avg-1-chunk-64-left-128.int8.onnx`, `tokens.txt`
    - 말하는 도중에는 `partial` 이벤트를 내고, 끝점을 감지하면 `final` 이벤트를 낸다.
  - `SenseVoiceRecognizer(model_dir: Path, vad_model: Path, *, num_threads: int = 2, min_silence: float = 0.5, max_speech: float = 15.0)`, `name = "SenseVoice"`
    - 모델: `models/sensevoice/model.int8.onnx`, `tokens.txt`, VAD `models/vad/silero_vad.onnx`
    - `final` 이벤트만 낸다.

이 두 파일은 sherpa-onnx를 얇게 감싼 것이라 단위 테스트를 두지 않는다. 실제 모델 테스트로 확인하고, 모델이 없으면 건너뛴다. 테스트 음성은 SenseVoice 압축 파일에 들어 있는 `test_wavs/ko.wav`를 쓴다.

- [ ] **Step 1: 실제 모델 테스트 작성**

`tests/test_asr_engines.py`:

```python
import re

import pytest

from sukpago.asr.base import SAMPLE_RATE, load_wav_16k_mono

HANGUL = re.compile(r"[가-힣]")


def run(rec, samples):
    finals = []
    step = SAMPLE_RATE // 10
    for i in range(0, len(samples), step):
        finals += [e.text for e in rec.accept(samples[i:i + step]) if e.kind == "final"]
    finals += [e.text for e in rec.finish() if e.kind == "final"]
    return " ".join(finals)


@pytest.mark.models
def test_zipformer_recognizes_korean(model_path):
    from sukpago.asr.zipformer import ZipformerRecognizer

    wav = model_path("sensevoice", "test_wavs", "ko.wav")
    rec = ZipformerRecognizer(model_path("zipformer-ko"))
    text = run(rec, load_wav_16k_mono(wav))
    assert HANGUL.search(text), text


@pytest.mark.models
def test_zipformer_emits_partials(model_path):
    from sukpago.asr.zipformer import ZipformerRecognizer

    samples = load_wav_16k_mono(model_path("sensevoice", "test_wavs", "ko.wav"))
    rec = ZipformerRecognizer(model_path("zipformer-ko"))
    kinds = set()
    for i in range(0, len(samples), SAMPLE_RATE // 10):
        kinds |= {e.kind for e in rec.accept(samples[i:i + SAMPLE_RATE // 10])}
    assert "partial" in kinds


@pytest.mark.models
def test_sensevoice_recognizes_korean(model_path):
    from sukpago.asr.sensevoice import SenseVoiceRecognizer

    rec = SenseVoiceRecognizer(model_path("sensevoice"), model_path("vad", "silero_vad.onnx"))
    text = run(rec, load_wav_16k_mono(model_path("sensevoice", "test_wavs", "ko.wav")))
    assert HANGUL.search(text), text
```

- [ ] **Step 2: 테스트가 건너뛰어지는지 확인**

Run: `uv run pytest tests/test_asr_engines.py -v`
Expected: 3 skipped ("모델 없음"). 모델을 받은 뒤 Task 12에서 다시 돌린다.

- [ ] **Step 3: 구현**

`src/sukpago/asr/zipformer.py`:

```python
"""스트리밍 한국어 음성 인식: kangkyu Zipformer (sherpa-onnx int8)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .base import SAMPLE_RATE, AsrEvent


class ZipformerRecognizer:
    name = "Zipformer"

    def __init__(self, model_dir: Path, *, chunk: int = 64, num_threads: int = 2) -> None:
        import sherpa_onnx

        model_dir = Path(model_dir)

        def part(kind: str) -> str:
            return str(model_dir / f"{kind}-epoch-99-avg-1-chunk-{chunk}-left-128.int8.onnx")

        self._rec = sherpa_onnx.OnlineRecognizer.from_transducer(
            tokens=str(model_dir / "tokens.txt"),
            encoder=part("encoder"), decoder=part("decoder"), joiner=part("joiner"),
            num_threads=num_threads, sample_rate=SAMPLE_RATE, feature_dim=80,
            enable_endpoint_detection=True,
            rule1_min_trailing_silence=1.2, rule2_min_trailing_silence=0.6,
            rule3_min_utterance_length=15.0,
            decoding_method="greedy_search",
        )
        self._pad_s = chunk * 0.04  # 모델 카드 권장: 끝에 CHUNK × 0.04초 무음
        self._stream = self._rec.create_stream()
        self._last = ""
        self._fed = 0

    def accept(self, samples: np.ndarray) -> list[AsrEvent]:
        samples = np.asarray(samples, dtype=np.float32)
        self._fed += len(samples)
        self._stream.accept_waveform(SAMPLE_RATE, samples)
        while self._rec.is_ready(self._stream):
            self._rec.decode_stream(self._stream)
        text = self._rec.get_result(self._stream).strip()
        t = self._fed / SAMPLE_RATE
        events: list[AsrEvent] = []
        if text != self._last:
            events.append(AsrEvent("partial", text, t))
            self._last = text
        if self._rec.is_endpoint(self._stream):
            if text:
                events.append(AsrEvent("final", text, t))
            self._rec.reset(self._stream)
            self._last = ""
        return events

    def finish(self) -> list[AsrEvent]:
        pad = np.zeros(int(self._pad_s * SAMPLE_RATE), dtype=np.float32)
        self._stream.accept_waveform(SAMPLE_RATE, pad)
        self._stream.input_finished()
        while self._rec.is_ready(self._stream):
            self._rec.decode_stream(self._stream)
        text = self._rec.get_result(self._stream).strip()
        self._stream = self._rec.create_stream()
        self._last = ""
        return [AsrEvent("final", text, self._fed / SAMPLE_RATE)] if text else []
```

`src/sukpago/asr/sensevoice.py`:

```python
"""문장 단위 한국어 음성 인식: silero VAD + SenseVoice 2024-07-17 (sherpa-onnx int8)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .base import SAMPLE_RATE, AsrEvent, Framer


class SenseVoiceRecognizer:
    name = "SenseVoice"

    def __init__(self, model_dir: Path, vad_model: Path, *, num_threads: int = 2,
                 min_silence: float = 0.5, max_speech: float = 15.0) -> None:
        import sherpa_onnx

        model_dir = Path(model_dir)
        self._rec = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=str(model_dir / "model.int8.onnx"), tokens=str(model_dir / "tokens.txt"),
            language="ko", use_itn=True, num_threads=num_threads,
        )
        cfg = sherpa_onnx.VadModelConfig()
        cfg.silero_vad.model = str(vad_model)
        cfg.silero_vad.min_silence_duration = min_silence
        cfg.silero_vad.max_speech_duration = max_speech
        cfg.sample_rate = SAMPLE_RATE
        self._vad = sherpa_onnx.VoiceActivityDetector(cfg, buffer_size_in_seconds=60)
        self._framer = Framer(512)

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
            stream = self._rec.create_stream()
            stream.accept_waveform(SAMPLE_RATE, seg.samples)
            self._rec.decode_stream(stream)
            text = stream.result.text.strip()
            if text:
                events.append(AsrEvent("final", text, (seg.start + len(seg.samples)) / SAMPLE_RATE))
            self._vad.pop()
        return events
```

- [ ] **Step 4: 전체 테스트 확인**

Run: `uv run pytest -v`
Expected: 모델 없는 테스트는 모두 통과하고, `models` 테스트는 skipped

- [ ] **Step 5: 커밋**

```bash
git add src/sukpago/asr/zipformer.py src/sukpago/asr/sensevoice.py tests/test_asr_engines.py
git commit -m "feat: Zipformer와 SenseVoice 음성 인식 엔진 추가"
```

---

### Task 11: 품질 검사 함수 (전통 문자, 반복, 메모리)

**Files:**
- Create: `src/sukpago/quality.py`, `tests/test_quality.py`

**Interfaces:**
- Produces:
  - `has_traditional_mongolian(text) -> bool` (U+1800–U+18AF가 있으면 True)
  - `is_cyrillic_mongolian(text) -> bool` (키릴 문자가 있고 전통 문자가 없으면 True)
  - `has_repetition(text, n=3, times=3) -> bool`: 같은 n-그램이 `times`번 이상 나오면 True. 공백이 있으면 단어 단위, 없으면 글자 단위로 센다.
  - `peak_rss_mb() -> float`: 이 프로세스의 최대 메모리. Windows에서는 `peak_wset`, 그 밖에는 `ru_maxrss`를 쓴다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_quality.py`:

```python
from sukpago.quality import (has_repetition, has_traditional_mongolian, is_cyrillic_mongolian,
                             peak_rss_mb)


def test_mongolian_script_detection():
    assert is_cyrillic_mongolian("Анхаарлаа төвлөрүүл.")
    assert not has_traditional_mongolian("Анхаарлаа төвлөрүүл.")
    trad = "ᠮᠣᠩᠭᠣᠯ ᠬᠡᠯᠡ"
    assert has_traditional_mongolian(trad)
    assert not is_cyrillic_mongolian(trad)
    assert not is_cyrillic_mongolian("Please focus.")


def test_repetition_words():
    loop = ("it's really easy to go to a website that explains virtue, and it's really easy to go "
            "to a website that explains virtue, and it's really easy to go to a website")
    assert has_repetition(loop)
    assert not has_repetition("Please submit your homework by next Tuesday.")


def test_repetition_chars_for_chinese():
    assert has_repetition("解释论文解释论文解释论文")
    assert not has_repetition("请在下周二之前提交作业。")


def test_peak_rss_is_plausible():
    assert 10 < peak_rss_mb() < 100_000
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `uv run pytest tests/test_quality.py -v`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: 구현**

`src/sukpago/quality.py`:

```python
"""번역 결과 품질 검사와 메모리 측정 (평가와 CI 스모크 테스트에서 씀)."""

from __future__ import annotations

import re
import sys
from collections import Counter

_TRAD_MN = re.compile(r"[\u1800-\u18AF]")
_CYRILLIC = re.compile(r"[\u0400-\u04FF]")


def has_traditional_mongolian(text: str) -> bool:
    return bool(_TRAD_MN.search(text))


def is_cyrillic_mongolian(text: str) -> bool:
    return bool(_CYRILLIC.search(text)) and not has_traditional_mongolian(text)


def has_repetition(text: str, n: int = 3, times: int = 3) -> bool:
    stripped = text.strip()
    units = stripped.split() if " " in stripped else list(stripped)
    if len(units) < n * times:
        return False
    counts = Counter(tuple(units[i:i + n]) for i in range(len(units) - n + 1))
    return max(counts.values()) >= times


def peak_rss_mb() -> float:
    if sys.platform == "win32":
        import psutil

        return psutil.Process().memory_info().peak_wset / 2**20
    import resource

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / 2**20 if sys.platform == "darwin" else peak / 1024
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_quality.py -v`
Expected: 4 passed

- [ ] **Step 5: 커밋**

```bash
git add src/sukpago/quality.py tests/test_quality.py
git commit -m "feat: 몽골어 문자·반복 검사와 메모리 측정 함수 추가"
```

---

### Task 12: 모델 받기 (models.lock.json, download_models.py)

**Files:**
- Create: `tools/models.lock.json`, `tools/download_models.py`, `tests/test_download_models.py`

**Interfaces:**
- Produces:
  - `download_models.LOCK: Path`
  - `sha256_file(path) -> str`, `is_valid(path, sha256, size) -> bool`
  - `download(url, dest, sha256, size, opener=_open) -> None`: 이미 맞는 파일이 있으면 건너뛴다. 해시가 틀리면 `.part` 파일을 지우고 `RuntimeError`를 낸다.
  - `extract_stripped(archive, dest) -> None`: tar.bz2를 풀면서 맨 위 폴더 하나를 벗긴다. 경로 탈출은 `tarfile.FilterError`로 막는다.
  - `fetch_model(name, spec, root, opener=_open) -> None`
  - CLI: `uv run python tools/download_models.py [이름 ...] [--dest models]`
  - 받은 결과는 `models/nllb-600m/`, `models/hymt2/`, `models/zipformer-ko/`, `models/sensevoice/`, `models/vad/`에 놓인다.

- [ ] **Step 1: `tools/models.lock.json` 작성**

아래 값은 2026-11-24에 Hugging Face API와 GitHub 릴리스에서 직접 확인했다. Hugging Face 주소는 커밋 해시로 고정했다.

```json
{
  "models": {
    "nllb-600m": {
      "dir": "nllb-600m",
      "files": [
        {"name": "config.json", "size": 159,
         "sha256": "0c2f6fa2057c7264d052fb4a62ba3476eeae70487acddfa8e779a53a00cbf44c",
         "url": "https://huggingface.co/JustFrederik/nllb-200-distilled-600M-ct2-int8/resolve/302d78f00e6fdb50a1064059df7c392b735e9d05/config.json"},
        {"name": "model.bin", "size": 622595991,
         "sha256": "ed1beaf75134de7505315a5223162f56acff397eff6b50638a500d3936fe707b",
         "url": "https://huggingface.co/JustFrederik/nllb-200-distilled-600M-ct2-int8/resolve/302d78f00e6fdb50a1064059df7c392b735e9d05/model.bin"},
        {"name": "sentencepiece.bpe.model", "size": 4852054,
         "sha256": "14bb8dfb35c0ffdea7bc01e56cea38b9e3d5efcdcb9c251d6b40538e1aab555a",
         "url": "https://huggingface.co/JustFrederik/nllb-200-distilled-600M-ct2-int8/resolve/302d78f00e6fdb50a1064059df7c392b735e9d05/sentencepiece.bpe.model"},
        {"name": "shared_vocabulary.txt", "size": 2568098,
         "sha256": "a132a83330f45514c2476eb81d1d69b3c41762264d16ce0a7ea982e5d6c728e5",
         "url": "https://huggingface.co/JustFrederik/nllb-200-distilled-600M-ct2-int8/resolve/302d78f00e6fdb50a1064059df7c392b735e9d05/shared_vocabulary.txt"}
      ]
    },
    "hymt2-q4": {
      "dir": "hymt2",
      "files": [
        {"name": "Hy-MT2-1.8B-Q4_K_M.gguf", "size": 1133080448,
         "sha256": "dc5f44fcf1fa496ee7ad725982c0c8c553a4de00259b53af84c4b89fb0c06699",
         "url": "https://huggingface.co/tencent/Hy-MT2-1.8B-GGUF/resolve/a0c709d9fac510f2c807aa3af52872340dc37a4a/Hy-MT2-1.8B-Q4_K_M.gguf"}
      ]
    },
    "zipformer-ko": {
      "dir": "zipformer-ko",
      "files": [
        {"name": "encoder-epoch-99-avg-1-chunk-64-left-128.int8.onnx", "size": 156826043,
         "sha256": "b8fb024cab6991f64ca5d2cecbd8a038c7c85fc95593f4bf90f86afd91eacf76",
         "url": "https://huggingface.co/kangkyu/icefall-asr-ko-streaming-zipformer-174m/resolve/f0e73b1653c3ea75898c6d949dd71c690c9121da/encoder-epoch-99-avg-1-chunk-64-left-128.int8.onnx"},
        {"name": "decoder-epoch-99-avg-1-chunk-64-left-128.int8.onnx", "size": 1544210,
         "sha256": "f5dfa6c8609b29da86c739d4904889475c33b62e28e70c619952a0ee6c31416f",
         "url": "https://huggingface.co/kangkyu/icefall-asr-ko-streaming-zipformer-174m/resolve/f0e73b1653c3ea75898c6d949dd71c690c9121da/decoder-epoch-99-avg-1-chunk-64-left-128.int8.onnx"},
        {"name": "joiner-epoch-99-avg-1-chunk-64-left-128.int8.onnx", "size": 1270777,
         "sha256": "64efd9aeb71fb2278c713b3d5eb5ec45edf6b2ccd8716d3709044f17723c13fd",
         "url": "https://huggingface.co/kangkyu/icefall-asr-ko-streaming-zipformer-174m/resolve/f0e73b1653c3ea75898c6d949dd71c690c9121da/joiner-epoch-99-avg-1-chunk-64-left-128.int8.onnx"},
        {"name": "tokens.txt", "size": 20844,
         "sha256": "435dfb9e0a2b6a79124f1a4d8f0f33a951b25384726e2e0d854f081533e6ec9d",
         "url": "https://huggingface.co/kangkyu/icefall-asr-ko-streaming-zipformer-174m/resolve/f0e73b1653c3ea75898c6d949dd71c690c9121da/tokens.txt"}
      ]
    },
    "sensevoice-ko": {
      "dir": "sensevoice",
      "archive": {"size": 163002883,
        "sha256": "7d1efa2138a65b0b488df37f8b89e3d91a60676e416f515b952358d83dfd347e",
        "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17.tar.bz2"}
    },
    "silero-vad": {
      "dir": "vad",
      "files": [
        {"name": "silero_vad.onnx", "size": 643854,
         "sha256": "9e2449e1087496d8d4caba907f23e0bd3f78d91fa552479bb9c23ac09cbb1fd6",
         "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx"}
      ]
    }
  }
}
```

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/test_download_models.py`:

```python
import hashlib
import io
import json
import tarfile

import pytest

import download_models as dm


def blob(data):
    return hashlib.sha256(data).hexdigest(), len(data)


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def opener_for(data, calls):
    def op(url):
        calls.append(url)
        return FakeResp(data)

    return op


def test_download_verifies_and_skips_existing(tmp_path):
    data, calls = b"hello", []
    sha, size = blob(data)
    dest = tmp_path / "m" / "f.bin"
    dm.download("u", dest, sha, size, opener_for(data, calls))
    assert dest.read_bytes() == data
    dm.download("u", dest, sha, size, opener_for(data, calls))
    assert calls == ["u"]


def test_download_rejects_bad_hash(tmp_path):
    sha, size = blob(b"good")
    dest = tmp_path / "f.bin"
    with pytest.raises(RuntimeError, match="불일치"):
        dm.download("u", dest, sha, size, opener_for(b"evil", []))
    assert not dest.exists()
    assert not (tmp_path / "f.bin.part").exists()


def make_tar(path, members):
    with tarfile.open(path, "w:bz2") as tf:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))


def test_extract_strips_top_folder(tmp_path):
    arc = tmp_path / "a.tar.bz2"
    make_tar(arc, {"top/model.onnx": b"m", "top/sub/x.wav": b"w"})
    dest = tmp_path / "out"
    dm.extract_stripped(arc, dest)
    assert (dest / "model.onnx").read_bytes() == b"m"
    assert (dest / "sub" / "x.wav").exists()


def test_extract_blocks_path_traversal(tmp_path):
    arc = tmp_path / "a.tar.bz2"
    make_tar(arc, {"../evil.txt": b"x"})
    with pytest.raises(tarfile.FilterError):
        dm.extract_stripped(arc, tmp_path / "out")
    assert not (tmp_path.parent / "evil.txt").exists()


def test_lock_file_is_complete():
    lock = json.loads(dm.LOCK.read_text("utf-8"))["models"]
    assert set(lock) == {"nllb-600m", "hymt2-q4", "zipformer-ko", "sensevoice-ko", "silero-vad"}
    for spec in lock.values():
        entries = spec.get("files", []) + ([spec["archive"]] if "archive" in spec else [])
        assert entries
        for e in entries:
            assert len(e["sha256"]) == 64 and e["size"] > 0
            assert e["url"].startswith("https://")
            assert "/resolve/main/" not in e["url"]
```

- [ ] **Step 3: 테스트가 실패하는지 확인**

Run: `uv run pytest tests/test_download_models.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'download_models'`)

- [ ] **Step 4: 구현**

`tools/download_models.py`:

```python
"""models.lock.json에 적힌 모델을 받아 크기와 SHA256을 확인한다.

사용: uv run python tools/download_models.py [이름 ...] [--dest models]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

LOCK = Path(__file__).with_name("models.lock.json")
CHUNK = 1 << 20


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def is_valid(path: Path, sha256: str, size: int) -> bool:
    return path.is_file() and path.stat().st_size == size and sha256_file(path) == sha256


def _open(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "SukPaGo-model-downloader"})
    return urllib.request.urlopen(req, timeout=60)


def download(url: str, dest: Path, sha256: str, size: int, opener=_open) -> None:
    if is_valid(dest, sha256, size):
        print(f"  있음  {dest.name}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    h, n = hashlib.sha256(), 0
    with opener(url) as resp, open(part, "wb") as out:
        for block in iter(lambda: resp.read(CHUNK), b""):
            out.write(block)
            h.update(block)
            n += len(block)
    if n != size or h.hexdigest() != sha256:
        part.unlink(missing_ok=True)
        raise RuntimeError(f"{dest.name}: 크기 또는 SHA256 불일치 (받은 크기 {n}, 기대 {size})")
    part.replace(dest)
    print(f"  받음  {dest.name} ({n / 2**20:.0f}MB)")


def extract_stripped(archive: Path, dest: Path) -> None:
    """tar.bz2를 풀되 맨 위 폴더 하나를 벗긴다. 경로 탈출은 tarfile의 data 필터가 막는다."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=dest.parent) as tmp:
        with tarfile.open(archive, "r:bz2") as tf:
            tf.extractall(tmp, filter="data")
        roots = list(Path(tmp).iterdir())
        src = roots[0] if len(roots) == 1 and roots[0].is_dir() else Path(tmp)
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True)
        for child in src.iterdir():
            shutil.move(str(child), dest / child.name)


def fetch_model(name: str, spec: dict, root: Path, opener=_open) -> None:
    print(f"[{name}]")
    target = root / spec["dir"]
    for f in spec.get("files", []):
        download(f["url"], target / f["name"], f["sha256"], f["size"], opener)
    archive = spec.get("archive")
    if archive:
        stamp = target / ".archive-sha256"
        if stamp.is_file() and stamp.read_text().strip() == archive["sha256"]:
            print("  있음  (압축 해제됨)")
            return
        tmp = root / f".{name}.tar.bz2"
        download(archive["url"], tmp, archive["sha256"], archive["size"], opener)
        extract_stripped(tmp, target)
        tmp.unlink()
        stamp.write_text(archive["sha256"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="석파고 모델 받기")
    parser.add_argument("names", nargs="*", help="받을 모델 이름 (생략하면 전부)")
    parser.add_argument("--dest", type=Path, default=Path(__file__).resolve().parents[1] / "models")
    args = parser.parse_args(argv)
    lock = json.loads(LOCK.read_text("utf-8"))["models"]
    names = args.names or list(lock)
    unknown = [n for n in names if n not in lock]
    if unknown:
        print(f"모르는 모델: {unknown}. 가능한 이름: {list(lock)}", file=sys.stderr)
        return 2
    for name in names:
        fetch_model(name, lock[name], args.dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `uv run pytest tests/test_download_models.py -v`
Expected: 5 passed

- [ ] **Step 6: 실제 모델 받기와 실제 모델 테스트**

Run: `uv run python tools/download_models.py`
Expected: 다섯 모델이 모두 "받음"(약 2.1GB)으로 끝난다. 다시 실행하면 모두 "있음"이 나온다.

Run: `uv run pytest -v`
Expected: 모든 테스트 통과, skipped 0개.
- Zipformer 테스트가 실패하면 출력된 인식 결과를 기록하고, `num_threads`와 청크 설정을 확인한다.
- Hy-MT2 테스트가 빈 결과로 실패하면 `Llama` 로드 로그를 보기 위해 `verbose=True`로 한 번 실행해 본다.

- [ ] **Step 7: 커밋**

```bash
git add tools/models.lock.json tools/download_models.py tests/test_download_models.py
git commit -m "feat: SHA256으로 검증하는 모델 다운로드 도구 추가"
```

---

### Task 13: 평가 도구 (evaluate.py)

**Files:**
- Create: `tools/evaluate.py`, `tests/test_evaluate.py`

**Interfaces:**
- Consumes:
  - `ZipformerRecognizer`, `SenseVoiceRecognizer` (Task 10), `HyMtTranslator` (Task 6), `NllbTranslator` (Task 5)
  - `SentenceAssembler` (Task 3), `load_wav_16k_mono`, `SAMPLE_RATE` (Task 9)
  - `has_repetition`, `has_traditional_mongolian`, `is_cyrillic_mongolian`, `peak_rss_mb` (Task 11)
  - `paths.models_dir()` (Task 1)
- Produces:
  - `run_asr(rec, samples) -> dict`: 키 `finals`, `sentences`, `compute_s`, `audio_s`
  - `flags(row: dict) -> str`, `cell(s: str) -> str`
  - CLI: `uv run python tools/evaluate.py [--wav-dir eval_data] [--out eval_out]` → `eval_out/report.md`
  - 내부 하위 프로세스 모드 `--worker asr|mt|combo ...`: 엔진마다 메모리를 따로 재기 위해 쓴다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_evaluate.py`:

```python
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
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `uv run pytest tests/test_evaluate.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'evaluate'`)

- [ ] **Step 3: 구현**

`tools/evaluate.py`:

```python
"""실제 강의 녹음으로 음성 인식·번역 후보를 비교한다.

사용: uv run python tools/evaluate.py [--wav-dir eval_data] [--out eval_out]
결과(eval_out/)에는 강의 내용이 들어가므로 커밋하지 않는다.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from sukpago import paths
from sukpago.asr.base import SAMPLE_RATE, load_wav_16k_mono
from sukpago.languages import TARGET_ORDER
from sukpago.quality import has_repetition, has_traditional_mongolian, is_cyrillic_mongolian, peak_rss_mb
from sukpago.text.assembler import SentenceAssembler

ASR_CANDIDATES = ("zipformer", "sensevoice")
MT_CANDIDATES = ("hymt", "nllb")
STEP = SAMPLE_RATE // 10  # 마이크처럼 0.1초씩 넣는다
BUDGET_MB = 1800


def make_asr(name: str):
    m = paths.models_dir()
    if name == "zipformer":
        from sukpago.asr.zipformer import ZipformerRecognizer
        return ZipformerRecognizer(m / "zipformer-ko")
    from sukpago.asr.sensevoice import SenseVoiceRecognizer
    return SenseVoiceRecognizer(m / "sensevoice", m / "vad" / "silero_vad.onnx")


def make_mt(name: str):
    m = paths.models_dir()
    if name == "hymt":
        from sukpago.translate.hymt import HyMtTranslator
        return HyMtTranslator(m / "hymt2" / "Hy-MT2-1.8B-Q4_K_M.gguf")
    from sukpago.translate.nllb import NllbTranslator
    return NllbTranslator(m / "nllb-600m")


def run_asr(rec, samples: np.ndarray) -> dict:
    asm = SentenceAssembler()
    finals: list[str] = []
    sentences: list[str] = []
    t0 = time.perf_counter()
    for i in range(0, len(samples), STEP):
        for ev in rec.accept(samples[i:i + STEP]):
            if ev.kind == "final":
                finals.append(ev.text)
                sentences += asm.feed(ev.text, ev.t)
        sentences += asm.tick((i + STEP) / SAMPLE_RATE)
    for ev in rec.finish():
        if ev.kind == "final":
            finals.append(ev.text)
            sentences += asm.feed(ev.text, ev.t)
    sentences += asm.flush()
    return {"finals": finals, "sentences": sentences,
            "compute_s": time.perf_counter() - t0, "audio_s": len(samples) / SAMPLE_RATE}


def translate_rows(tr, sentences: list[str]) -> list[dict]:
    rows = []
    for ko in sentences:
        row: dict = {"ko": ko}
        for lang in TARGET_ORDER:
            t0 = time.perf_counter()
            try:
                row[lang] = tr.translate(ko, lang)
            except Exception as e:  # 평가 보고서에 실패도 남긴다
                row[lang] = f"[오류] {e}"
            row[f"{lang}_ms"] = round((time.perf_counter() - t0) * 1000)
        rows.append(row)
    return rows


def flags(row: dict) -> str:
    found = []
    mn = row.get("mn", "")
    if has_traditional_mongolian(mn):
        found.append("몽골어 전통 문자")
    elif not is_cyrillic_mongolian(mn):
        found.append("몽골어 키릴 아님")
    found += [f"{lang} 반복" for lang in TARGET_ORDER if has_repetition(row.get(lang, ""))]
    return ", ".join(found) or "-"


def cell(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ")


def worker(argv: list[str]) -> dict:
    kind = argv[0]
    if kind == "asr":
        out = run_asr(make_asr(argv[1]), load_wav_16k_mono(Path(argv[2])))
    elif kind == "mt":
        sentences = json.loads(Path(argv[2]).read_text("utf-8"))
        out = {"rows": translate_rows(make_mt(argv[1]), sentences)}
    elif kind == "combo":
        rec, tr = make_asr(argv[1]), make_mt(argv[2])
        run_asr(rec, load_wav_16k_mono(Path(argv[3]))[:60 * SAMPLE_RATE])
        translate_rows(tr, json.loads(Path(argv[4]).read_text("utf-8"))[:3])
        out = {}
    else:
        raise SystemExit(f"모르는 worker 종류: {kind}")
    out["peak_mb"] = peak_rss_mb()
    return out


def call_worker(args: list[str]) -> dict:
    proc = subprocess.run([sys.executable, __file__, "--worker", *args],
                          capture_output=True, text=True, encoding="utf-8")
    lines = proc.stdout.strip().splitlines()
    if proc.returncode != 0 or not lines:
        err = proc.stderr.strip().splitlines()
        return {"error": err[-1] if err else f"종료 코드 {proc.returncode}"}
    return json.loads(lines[-1])


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        print(json.dumps(worker(sys.argv[2:]), ensure_ascii=False))
        return 0
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="석파고 모델 평가")
    parser.add_argument("--wav-dir", type=Path, default=root / "eval_data")
    parser.add_argument("--out", type=Path, default=root / "eval_out")
    args = parser.parse_args()
    wavs = sorted(args.wav_dir.glob("*.wav"))
    if not wavs:
        print(f"{args.wav_dir}에 16kHz 모노 wav를 넣으세요", file=sys.stderr)
        return 2
    args.out.mkdir(parents=True, exist_ok=True)
    lines = ["# 석파고 모델 평가", ""]

    asr_results: dict[tuple[str, str], dict] = {}
    for eng in ASR_CANDIDATES:
        lines += [f"## 음성 인식: {eng}", ""]
        for wav in wavs:
            print(f"음성 인식 {eng} · {wav.name}")
            r = call_worker(["asr", eng, str(wav)])
            asr_results[(eng, wav.name)] = r
            if "error" in r:
                lines += [f"- {wav.name}: 실행 실패 — {r['error']}", ""]
                continue
            lines += [f"### {wav.name}",
                      f"- 실시간 배율(RTF) {r['compute_s'] / r['audio_s']:.3f} · "
                      f"최대 메모리 {r['peak_mb']:.0f}MB · 문장 {len(r['sentences'])}개", ""]
            lines += [f"{i + 1}. {s}" for i, s in enumerate(r["sentences"])] + [""]

    pick: list[str] = []
    for eng in ASR_CANDIDATES:
        for wav in wavs:
            pick += [s for s in asr_results.get((eng, wav.name), {}).get("sentences", []) if len(s) >= 12]
        if pick:
            break
    sent_file = args.out / "sentences.json"
    sent_file.write_text(json.dumps(pick[:10], ensure_ascii=False), "utf-8")

    for eng in MT_CANDIDATES:
        print(f"번역 {eng}")
        r = call_worker(["mt", eng, str(sent_file)])
        lines += [f"## 번역: {eng}", ""]
        if "error" in r:
            lines += [f"실행 실패 — {r['error']}", ""]
            continue
        lines += [f"최대 메모리 {r['peak_mb']:.0f}MB", "",
                  "| 한국어 | 몽골어 | 중국어 | 영어 | 시간 ms (mn/zh/en) | 경고 |",
                  "|---|---|---|---|---|---|"]
        for row in r["rows"]:
            ms = "/".join(str(row[f"{lang}_ms"]) for lang in TARGET_ORDER)
            cells = " | ".join(cell(row.get(k, "")) for k in ("ko", "mn", "zh", "en"))
            lines.append(f"| {cells} | {ms} | {flags(row)} |")
        lines.append("")

    lines += [f"## 함께 올렸을 때 최대 메모리 (1분 인식 + 3문장 번역, 목표 {BUDGET_MB}MB 이하)", ""]
    for a in ASR_CANDIDATES:
        for m in MT_CANDIDATES:
            print(f"메모리 {a} + {m}")
            r = call_worker(["combo", a, m, str(wavs[0]), str(sent_file)])
            if "error" in r:
                lines.append(f"- {a} + {m}: 실행 실패 — {r['error']}")
            else:
                over = " (목표 초과)" if r["peak_mb"] > BUDGET_MB else ""
                lines.append(f"- {a} + {m}: {r['peak_mb']:.0f}MB{over}")
    report = args.out / "report.md"
    report.write_text("\n".join(lines) + "\n", "utf-8")
    print(f"보고서: {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_evaluate.py -v`
Expected: 3 passed

- [ ] **Step 5: 커밋**

```bash
git add tools/evaluate.py tests/test_evaluate.py
git commit -m "feat: 강의 녹음으로 엔진 후보를 비교하는 평가 도구 추가"
```

---

### Task 14: 평가 실행과 엔진 결정

**Files:**
- Modify: `assets/engines.json`, `docs/superpowers/specs/2026-11-24-sukpago-design.md` (3장 엔진 표, 4장 결과, 6장 메모리 예산)
- 커밋하지 않음: `eval_data/`, `eval_out/`

**Interfaces:**
- Consumes: Task 12의 모델, Task 13의 `tools/evaluate.py`
- Produces: 확정된 `assets/engines.json`. 계획 2와 3은 이 파일과 설계 문서의 갱신된 표를 기준으로 쓴다.

- [ ] **Step 1: 강의 녹음 준비**

학생이 녹음한 강의 3개의 앞 3분을 16kHz 모노 wav로 만들어 `eval_data/`에 넣는다(이 폴더는 gitignore 대상).

```bash
mkdir -p eval_data
```

```bash
ffmpeg -v error -i "<강의1 원본>.webm" -t 180 -ac 1 -ar 16000 eval_data/lec1.wav
```

강의 2와 3도 같은 명령으로 `lec2.wav`, `lec3.wav`를 만든다.

- [ ] **Step 2: 평가 실행**

Run: `uv run python tools/evaluate.py`
Expected: 끝에 `보고서: …/eval_out/report.md`가 출력된다. 전체 소요 시간은 10~20분이다(Hy-MT2 30문장 번역 포함).

- [ ] **Step 3: 사용자와 보고서 검토**

`eval_out/report.md`를 사용자와 함께 보고 다음을 정한다. 판정 기준은 설계 문서 4장을 따른다.

1. **음성 인식:** Zipformer와 SenseVoice 중 "읽어서 뜻이 통하는 문장" 비율이 높은 쪽을 고른다. 띄어쓰기 여부도 함께 본다.
2. **번역:** 언어마다 Hy-MT2와 NLLB 중 하나를 고른다.
   - 몽골어 경고("전통 문자", "키릴 아님")가 있는 엔진은 몽골어에 쓰지 않는다.
   - "반복" 경고가 많은 엔진은 뺀다.
3. **메모리:** 고른 조합의 "함께 올렸을 때 최대 메모리"가 1800MB 이하인지 확인한다.
   - 넘으면 다른 조합을 고른다.
   - 모든 조합이 넘으면 사용자에게 알리고, 계획 2 전에 대응 방법을 정한다.

- [ ] **Step 4: 결정 반영**

`assets/engines.json`을 Step 3에서 고른 값으로 바꾼다. 예: 몽골어만 NLLB인 경우

```json
{
  "asr": "zipformer",
  "offline_mt": {"mn": "nllb", "zh": "hymt", "en": "hymt"}
}
```

설계 문서를 다음과 같이 고친다. 이력 표기 없이 현재 사실만 적는다.

- **3장 엔진 표:** "1순위 후보 / 대체" 열을 "사용 / 대체"로 바꾸고, 고른 엔진을 적는다.
- **3장 사실 목록:** 다음 측정값으로 바꾼다.
  - 평가에서 잰 RTF와 최대 메모리
  - Hy-MT2 몽골어가 키릴 문자로 나오는지
- **3장 언어 코드 표:** Hy-MT2 중국어 이름을 `中文`으로 바꾼다.
- **5장 반복 방지:** Hy-MT2 `max_tokens`를 `입력 토큰 × 3 + 16`으로 바꾼다.
- **5장 문장 정리:** 용어 사전 치환은 구현됐고 Zipformer 핫워드는 계획 2에서 시험한다고 적는다.
- **6장 메모리 예산 표:** 측정값으로 바꾼다.

- [ ] **Step 5: 전체 테스트와 커밋**

Run: `uv run pytest -v`
Expected: 전부 통과 (`test_repo_engines_json_is_valid` 포함)

```bash
git add assets/engines.json docs/superpowers/specs/2026-11-24-sukpago-design.md
git commit -m "docs: 강의 녹음 평가 결과로 엔진 확정"
```
