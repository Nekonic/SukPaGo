# 석파고 계획 2: 앱 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 설계 문서(`docs/superpowers/specs/2026-11-24-sukpago-design.md`)의 tkinter 앱을 완성한다. 구성 요소는 다음과 같다.
- 설정·사용자 데이터
- 무료 API 번역(MyMemory, 대체 NLLB-600M)
- edge-tts 음성과 재생
- 마이크
- 파이프라인
- 메인 창과 번역 전용 창
- `run.py` 한 줄 실행
- exe 빌드와 CI

**Architecture:** 계획 1의 엔진(`src/sukpago/asr`, `text`, `translate`, `quality`, `engines`) 위에 올린다.
- 모든 작업이 아래 "공통 인터페이스"를 지킨다. 그래서 작업 W1~W6은 서로를 기다리지 않고 동시에 진행할 수 있다.
- 다른 작업의 모듈이 아직 없으면 테스트에서 가짜 객체를 쓴다.
- 마지막 작업 W7(조립)은 모든 작업이 합쳐진 뒤에 한다.

**Tech Stack:** Python 3.13, uv, pytest, CustomTkinter 6, miniaudio, edge-tts, sherpa-onnx 1.13.8, CTranslate2, PyInstaller. 의존성은 `d32dfdc`에서 이미 추가했다. `pyproject.toml`과 `uv.lock`은 W1~W6에서 고치지 않는다.

## Global Constraints

- 실행 환경은 Windows 10/11 64비트이고, 개발은 macOS에서 한다. OS별로 다른 동작(경로, 글꼴, 사용자 폴더)은 `sys.platform`으로 나눈다. 판단 기준은 Windows다.
- Python은 3.13이다. 모든 명령은 저장소 루트에서 `uv run ...`으로 실행한다.
- 카드와 API 키는 쓰지 않는다.
  - 번역은 MyMemory이고, 이메일 기본값은 `abcd@gmail.com`이다(사용자 지정).
  - 음성은 edge-tts다.
- 앱 메모리는 2GB 이하여야 한다. NLLB-600M은 대체가 처음 필요할 때만 올린다.
- 테스트는 모델·네트워크·마이크·스피커·화면 없이 돌아야 한다.
  - 실제 장치나 모델이 필요한 테스트는 `@pytest.mark.models`를 붙이거나, 조건이 안 되면 건너뛴다.
  - Tk 창이 필요한 테스트는 화면이 없으면(`tkinter.TclError`) 건너뛴다.
- 사용자 데이터는 `userdata.home()` 아래에 둔다. 테스트는 `SUKPAGO_HOME`을 `tmp_path`로 바꿔 쓴다.
- 문서에 변경 이력을 적지 않는다. 커밋 메시지는 한국어로 쓰고 `feat:`, `test:`, `fix:`, `chore:`, `docs:` 접두사를 붙인다.
- 각 작업은 테스트 작성 → 실패 확인 → 구현 → 통과 확인 → 커밋 순서로 진행한다(TDD). UI 그리기 코드처럼 자동 테스트가 어려운 부분은 순수 함수로 계산을 분리해 그 함수를 테스트한다.

## 공통 인터페이스

아래 이름과 형식은 바꾸지 않는다. 작업 사이의 약속이다.

### 이미 있는 것 (계획 1)

- `sukpago.languages`: `TARGET_ORDER = ("mn", "zh", "en")`, `get(lang).edge_voice`, `.name_ko`
- `sukpago.text.glossary.Glossary`: `.apply`, `.add`, `.remove`, `.rules`, `.to_json`, `.from_json`
- `sukpago.text.assembler.SentenceAssembler(glossary)`: `.feed(text, now)`, `.tick(now)`, `.flush()`, 속성 `.glossary`
- `sukpago.asr.base`: `SAMPLE_RATE = 16000`, `AsrEvent(kind, text, t)`, `Recognizer`(`accept`, `finish`)
- `sukpago.asr.zipformer.ZipformerRecognizer(model_dir)`
- `sukpago.translate.base`: `TranslateError`, `QuotaExceeded`
- `sukpago.translate.mymemory.MyMemoryTranslator(email, timeout, fetch)`
- `sukpago.translate.nllb.NllbTranslator(model_dir)`
- `sukpago.translate.router`: `RouteResult`, `TranslateRouter`
- `sukpago.engines.ModelManager`
- `sukpago.paths`: `app_root()`, `models_dir()`, `assets_dir()`

### 새로 만드는 것

```python
# sukpago/userdata.py  (W1)
def home() -> Path                    # SUKPAGO_HOME > Windows: %APPDATA%\SukPaGo > ~/.sukpago (없으면 만듦)
def read_json(name: str, default)     # 없거나 깨졌으면 default
def write_json(name: str, data) -> None   # 임시 파일에 쓰고 os.replace (원자적)

# sukpago/config.py  (W1)
@dataclass
class Settings:
    online: bool = True
    langs: list[str] = field(default_factory=lambda: ["mn", "zh"])
    read_aloud: bool = False
    pinned: bool = True
    mymemory_email: str = "abcd@gmail.com"
    mic_device: str | None = None
    main_geometry: str | None = None
    display_geometry: str | None = None
    display_font_px: int = 52
    display_prev_scale: float = 0.75
    display_pinned: bool = True
def load_settings() -> Settings        # settings.json. 모르는 키는 무시, 값 형식이 틀리면 그 항목만 기본값
def save_settings(s: Settings) -> None
def load_glossary() -> Glossary        # glossary.json, 없으면 기본 규칙 2개(노트북 에램→NotebookLM, 한강 리스크→할루시네이션 리스크)
def save_glossary(g: Glossary) -> None

# sukpago/phrases.py  (W1)
@dataclass(frozen=True)
class Phrase:
    key: str                  # 고정 "p1"~"p5", 내 문장 "c" + 13자리 밀리초 시각
    ko: str
    texts: dict[str, str]     # lang -> 번역
    custom: bool
def load_all() -> list[Phrase]                 # 고정 5개(assets/phrases.json) 다음에 내 문장(custom_phrases.json)
def add_custom(ko: str, texts: dict[str, str]) -> Phrase
def remove_custom(key: str) -> None            # json에서 빼고 그 문장의 mp3도 지움
def audio_path(phrase: Phrase, lang: str) -> Path
    # 고정: assets_dir()/"phrases"/f"{key}_{lang}.mp3"
    # 내 문장: home()/"phrases"/f"{key}_{lang}.mp3"

# sukpago/translate/router.py  (W1이 고침)
@dataclass(frozen=True)
class RouteResult:
    text: str
    engine: str
    fell_back: bool
    reason: str | None = None     # None | "error" | "quota" | "offline"
# TranslateRouter.translate(text, lang, *, online) 규칙 추가:
#   QuotaExceeded가 한 번 나면 reset_quota() 전까지 온라인을 건너뛰고 reason="quota"
#   일반 TranslateError면 그 요청만 reason="error"
#   online=False면 reason="offline", fell_back=False
# TranslateRouter.reset_quota() -> None, 속성 .quota_exceeded: bool

# sukpago/engines.py  (W1이 추가)
def make_router(email: str, models_dir: Path) -> TranslateRouter
    # 온라인 MyMemoryTranslator(email), 오프라인 ModelManager({"nllb600": NllbTranslator(models_dir/"nllb-600m")}),
    # 세 언어 모두 "nllb600"

# sukpago/tts/base.py, edge.py, cache.py  (W2)
class TtsError(Exception)
class Speaker(Protocol):
    name: str
    def synth(self, text: str, lang: str) -> bytes   # mp3 바이트, 실패하면 TtsError
class EdgeSpeaker:            # name = "edge-tts"
    def __init__(self, *, timeout: float = 10.0, communicate=None)
    # communicate(text, voice)는 edge_tts.Communicate와 같은 모양(.stream()이 {"type": "audio", "data": bytes}를 내는 async 반복자). 테스트에서 가짜로 바꿈
class CachedSpeaker:          # name = inner.name
    def __init__(self, inner: Speaker, max_items: int = 200)   # (text, lang) LRU

# sukpago/audio.py  (W2)
class AudioError(Exception)
class Player:
    def play(self, clips: list[bytes]) -> None   # mp3 또는 wav 바이트를 차례로, 바로 반환(비동기). 재생 중이면 멈추고 새로 시작
    def play_files(self, paths: list[Path]) -> None
    def stop(self) -> None
    @property
    def playing(self) -> bool
    # 재생 장치가 없으면 AudioError

# sukpago/asr/mic.py  (W3)
class MicError(Exception)
def list_devices() -> list[str]                  # 장치 이름 목록, 실패하면 []
def level(samples: np.ndarray) -> tuple[float, float]   # (dBFS, 클리핑 비율 |x|>=0.99), 빈 배열은 (-120.0, 0.0)
def classify(dbfs: float, clip_ratio: float) -> str     # "loud"(clip>=0.01) > "silent"(dbfs<-60) > "quiet"(dbfs<-40) > "ok"
class Mic:
    def __init__(self, device: str | None, on_samples: Callable[[np.ndarray], None], *, chunk_ms: int = 100)
    def start(self) -> None      # 16kHz 모노 float32로 캡처, chunk_ms마다 on_samples 호출(캡처 스레드에서). 실패하면 MicError
    def stop(self) -> None

# sukpago/models.py  (W4)
def ensure(role: str = "app", *, progress: Callable[[str, int, int], None] | None = None) -> list[str]
    # tools/models.lock.json의 roles[role]에 있는 모델을 models_dir()에 준비하고, 새로 받은 파일 이름 목록을 돌려줌
    # progress(파일이름, 받은 바이트, 전체 바이트)
# tools/download_models.py는 sukpago.models의 함수를 다시 쓰는 얇은 CLI가 된다(기존 테스트 유지).

# sukpago/pipeline.py  (W5)
@dataclass(frozen=True) class Partial:     text: str
@dataclass(frozen=True) class Final:       seq: int; ko: str; source: str   # "live" | "text"
@dataclass(frozen=True) class Translation: seq: int; lang: str; text: str; engine: str; fell_back: bool; reason: str | None
@dataclass(frozen=True) class Status:      kind: str; message: str
    # kind: "mic_error" | "fallback" | "quota" | "tts_error" | "audio_error" | "delay" | "info"
@dataclass(frozen=True) class MicLevel:    dbfs: float; clip_ratio: float; state: str
class Pipeline:
    def __init__(self, *, recognizer_factory: Callable[[], Recognizer], router, speaker: Speaker, player: Player,
                 mic_factory: Callable[[str | None, Callable[[np.ndarray], None]], Mic], settings: Settings,
                 glossary: Glossary, clock: Callable[[], float] = time.monotonic)
    events: queue.Queue          # UI가 꺼내 그리는 이벤트
    def start_live(self) -> None         # 마이크 열고 인식 시작. 실패하면 Status("mic_error")
    def stop_live(self) -> None          # 남은 조각까지 확정(finish, flush)
    @property
    def live(self) -> bool
    def submit_text(self, ko: str) -> int    # 직접 입력: Final(source="text") 후 번역, 번역이 끝나면 읽어 줌. seq 반환
    def speak(self, texts: dict[str, str]) -> None   # 켜진 언어만 TARGET_ORDER 순서로 합성해 재생(온라인일 때만)
    def play_phrase(self, phrase: Phrase) -> None    # mp3 파일 재생(켜진 언어 순서), 파일이 없고 온라인이면 합성
    def translate_once(self, ko: str) -> dict[str, str]   # 동기 번역(내 문장 추가용), 켜진 언어 전부
    def set_langs(self, langs: list[str]) -> None
    def set_online(self, online: bool) -> None
    def set_read_aloud(self, on: bool) -> None
    def set_glossary(self, g: Glossary) -> None
    def shutdown(self) -> None
```

---

### W1: 설정, 사용자 데이터, 고정 문장, 라우터 한도 처리, 정리

**Files:**
- Create:
  - `src/sukpago/userdata.py`, `src/sukpago/config.py`, `src/sukpago/phrases.py`, `assets/phrases.json`
  - 테스트: `tests/test_userdata.py`, `tests/test_config.py`, `tests/test_phrases.py`
- Modify:
  - `src/sukpago/translate/router.py`, `src/sukpago/engines.py`, `tools/evaluate.py`
  - 테스트: `tests/test_router.py`, `tests/test_engines.py`
- Delete: `src/sukpago/translate/hymt.py`, `src/sukpago/translate/gemma.py`, `tests/test_hymt.py`, `tests/test_gemma.py`

**할 일과 필수 테스트**
- `assets/phrases.json`: 설계 문서 11장 표의 5문장. 형식은 `[{"key": "p1", "ko": "...", "mn": "...", "zh": "...", "en": "..."}, ...]`이다.
- `userdata`
  - `SUKPAGO_HOME`이 있으면 그 경로를 쓴다.
  - `write_json` 뒤 `read_json`으로 한글이 그대로 돌아오는지 확인한다.
  - 깨진 JSON은 default를 돌려준다.
  - `write_json`이 남긴 임시 파일이 없어야 한다.
- `config`
  - 기본값을 확인한다. 이메일 기본값은 `abcd@gmail.com`이다.
  - 저장 후 불러온 값이 같아야 한다.
  - 모르는 키는 무시하고, 형식이 틀린 값(`"display_font_px": "big"`)은 그 항목만 기본값으로 둔다.
  - `load_glossary` 기본 규칙은 2개이고, 저장 후 불러온 값이 같아야 한다.
- `phrases`
  - `load_all()`에 고정 5개가 순서대로 있어야 한다.
  - `add_custom`은 key가 `c`로 시작하고 `custom=True`이며, 다시 `load_all()`에 나타나야 한다.
  - `remove_custom`은 json과 mp3를 둘 다 지운다(가짜 mp3 파일로 확인).
  - `audio_path`가 고정 문장과 내 문장에서 각각 맞는 경로를 내야 한다.
- `router`
  - 한도 초과 뒤 다음 요청은 온라인을 부르지 않고 `reason="quota"`, `fell_back=True`여야 한다.
  - `reset_quota()` 뒤에는 다시 온라인을 부른다.
  - 일반 오류는 그 요청만 `reason="error"`다.
  - 오프라인 모드는 `reason="offline"`, `fell_back=False`다.
  - 기존 테스트는 그대로 통과해야 한다(`reason` 기본값이 `None`).
- `engines.make_router`
  - 가짜 경로로 만들었을 때 온라인 엔진의 이름은 `"MyMemory"`이고 이메일이 전달되어야 한다.
  - 오프라인 엔진은 처음 쓸 때까지 만들어지지 않아야 한다.
- **정리:** Hy-MT2와 TranslateGemma 모듈과 테스트를 지운다.
  - `tools/evaluate.py`의 `MT_CANDIDATES`에서 `tgemma`, `tgemma_pivot`을 빼고 관련 import도 지운다.
  - `tools/models.lock.json`은 건드리지 않는다(W4 담당).
- **커밋:** 묶음마다 하나씩 커밋한다. 예: `feat: 설정과 사용자 데이터 저장 추가`, `feat: 고정 문장과 내 문장 관리 추가`, `feat: 번역 한도 초과 뒤 계속 대체 엔진 사용`, `chore: 쓰지 않는 Hy-MT2·TranslateGemma 코드 삭제`

### W2: edge-tts 음성, 캐시, 재생, 고정 문장 음성 만들기

**Files:**
- Create:
  - `src/sukpago/tts/__init__.py`, `src/sukpago/tts/base.py`, `src/sukpago/tts/edge.py`, `src/sukpago/tts/cache.py`
  - `src/sukpago/audio.py`, `tools/build_phrase_audio.py`
  - 테스트: `tests/test_tts.py`, `tests/test_audio.py`, `tests/test_build_phrase_audio.py`

**할 일과 필수 테스트**
- `EdgeSpeaker`
  - 언어별 음성 이름은 `languages.get(lang).edge_voice`를 쓴다.
  - 몽골어 원문은 그대로 보낸다. 글자 치환은 MMS 전용이라 여기서는 필요 없다.
  - asyncio 이벤트 루프는 호출한 스레드에서 `asyncio.run`으로 돌린다.
  - 가짜 `communicate`로 다음을 확인한다.
    - 오디오 조각이 이어 붙어 돌아오는지
    - 오디오가 비면 `TtsError`
    - 예외도 `TtsError`
    - 타임아웃도 `TtsError`
    - 넘긴 voice가 맞는지
- `CachedSpeaker`: 같은 (문장, 언어)면 inner를 한 번만 부른다. 201번째가 들어오면 가장 오래 안 쓴 것을 버린다.
- `Player`
  - miniaudio로 mp3와 wav를 디코딩한다(`miniaudio.decode`로 16비트 PCM).
  - 재생은 `miniaudio.PlaybackDevice`와 제너레이터로 하고, 여러 클립을 이어서 재생한다.
  - `stop()`은 즉시 멈춘다. `play()`는 이전 재생을 멈추고 새로 시작한다.
  - 장치를 만드는 부분은 주입할 수 있게 해서(`device_factory`), 가짜 장치로 다음을 테스트한다.
    - 클립 두 개가 순서대로 나오는지
    - stop 후 `playing`이 False인지
    - 장치가 없으면 `AudioError`
  - 디코딩 테스트용 wav는 `wave` 모듈로 만든다.
- `tools/build_phrase_audio.py`
  - `assets/phrases.json`의 5문장 × 3언어 mp3를 `assets/phrases/`에 만든다. 이미 있으면 건너뛴다.
  - `main(speaker=None)` 형태로 가짜 Speaker를 넣어 테스트한다.
  - 인터넷 실패는 경고만 하고 종료 코드 0으로 끝낸다.
  - `assets/phrases/*.mp3`는 `.gitignore`에 추가한다.
- **커밋:** `feat: edge-tts 음성과 캐시 추가`, `feat: mp3·wav 재생기 추가`, `feat: 고정 문장 음성 생성 도구 추가`

### W3: 마이크

**Files:**
- Create: `src/sukpago/asr/mic.py`, `tests/test_mic.py`

**할 일과 필수 테스트**
- `level`, `classify`: 공통 인터페이스의 값 경계를 테스트한다.
  - 사인파 0.5 진폭 → 약 −9dBFS, `ok`
  - 0.001 진폭 → `silent`
  - 0.005 진폭 → `quiet`
  - 1.0으로 가득 찬 배열 → `loud`
- `Mic`
  - `miniaudio.CaptureDevice(input_format=SampleFormat.FLOAT32, nchannels=1, sample_rate=16000)`와 제너레이터로 캡처한다.
  - 받은 샘플을 `chunk_ms` 단위로 모아 `on_samples`를 부른다.
  - 장치 이름이 주어지면 `miniaudio.Devices().get_captures()`에서 같은 이름의 id를 찾는다.
  - 장치를 만드는 부분은 주입할 수 있게 해서(`device_factory`), 가짜 장치로 다음을 테스트한다.
    - 250ms 분량을 넣으면 100ms 조각 2개가 나오는지
    - stop 후 콜백이 없는지
    - 열기 실패 시 `MicError`
  - `list_devices()`는 실패하면 `[]`다.
- **커밋:** `feat: 마이크 캡처와 소리 크기 판정 추가`

### W4: 모델 준비(`models.ensure`)와 `run.py`

**Files:**
- Create: `src/sukpago/models.py`, `run.py`, `tests/test_models.py`, `tests/test_run.py`
- Modify:
  - `tools/download_models.py`: 다운로드·검증·압축 해제 함수를 `sukpago.models`로 옮기고, 여기서는 다시 내보낸다. 기존 `tests/test_download_models.py`는 그대로 통과해야 한다.
  - `tools/models.lock.json`: 최상위에 `"roles": {"app": ["zipformer-ko", "nllb-600m"], "eval": [그 밖의 모든 모델 이름]}`을 추가한다.

**할 일과 필수 테스트**
- **검증 기록:** 검증을 통과한 파일 옆에 `<파일>.verified`(JSON `{"size", "mtime_ns", "sha256"}`)를 남긴다. 기록이 실제 파일과 맞으면 해시 계산을 건너뛴다.
  - 테스트: 해시 함수를 가짜로 바꿔 두 번째 호출에서 부르지 않는지 본다. 파일을 고치면 다시 계산하는지도 본다.
- **`ensure("app")`:** `roles.app`만 받는다.
  - 테스트: 가짜 opener와 가짜 lock으로, 없는 파일만 받고 progress가 불리는지 본다.
  - 모르는 role은 `KeyError`다.
- **`run.py`:** 표준 라이브러리만 쓴다. 맨 위에 `sys.version_info >= (3, 10)` 검사를 둔다.
  - `find_uv()`: `shutil.which("uv")` → `~/.local/bin/uv`(Windows `uv.exe`) → 없으면 None
  - `ensure_uv()`: 없으면 `[sys.executable, "-m", "pip", "install", "--user", "uv"]`를 실행한 뒤 다시 찾고, 그래도 없으면 안내 후 종료 코드 1
  - `main(argv)`
    - `setup`과 기본 실행 둘 다 다음을 차례로 실행한다.
      1. `uv sync --locked`
      2. `uv run python -c "from sukpago.models import ensure; ensure('app')"`
      3. `uv run python tools/build_phrase_audio.py`
    - 기본 실행은 이어서 `uv run python -m sukpago`를 실행하고 종료 코드를 돌려준다.
    - 단계마다 한 줄 안내를 출력한다(`[1/4] 환경 준비` 등).
  - 테스트: `subprocess.run`과 `shutil.which`를 가짜로 바꿔 다음을 확인한다.
    - 명령 순서
    - `setup`이면 앱 실행 명령이 없는지
    - uv가 없을 때 pip 설치를 시도하는지
    - 중간 단계가 실패하면 그 코드로 멈추는지
- **커밋:** `feat: 모델 준비 함수와 검증 기록 추가`, `feat: run.py 한 줄 실행 추가`

### W5: 파이프라인

**Files:**
- Create: `src/sukpago/pipeline.py`, `tests/test_pipeline.py`

**할 일과 필수 테스트** (공통 인터페이스 그대로)
- **스레드 구성**
  - 마이크 콜백은 오디오를 `audio_q`에 넣기만 한다.
  - 인식 스레드는 recognizer와 `SentenceAssembler(glossary)`를 돌리며 `Partial`과 `Final`을 낸다. 0.1초마다 `assembler.tick(clock())`을 부른다.
  - `MicLevel`은 0.2초에 한 번만 낸다.
  - 번역 스레드는 Final마다 켜진 언어를 `TARGET_ORDER` 순서로 번역해 `Translation`을 낸다.
  - 대체되면 `Status("fallback")`을 내고, 한도 초과는 처음 한 번만 `Status("quota")`를 낸다.
  - 번역 큐가 3개 이상 밀리면 `Status("delay")`를 낸다.
  - 읽기는 음성 스레드가 맡는다. 실시간 읽기가 켜져 있거나 `source="text"`이면 번역이 모두 끝난 뒤 `speak()`를 부른다.
  - `speak`·`play_phrase`의 TTS와 재생 오류는 `Status("tts_error")`와 `Status("audio_error")`로 바꾼다.
- **필수 테스트:** 가짜 recognizer·router·speaker·player·mic, 가짜 시계를 쓴다. 이벤트는 타임아웃 2초로 `events.get`을 기다린다.
  1. `start_live` 후 가짜 마이크가 샘플을 넣으면, 가짜 recognizer의 `partial`과 `final`이 `Partial` → `Final(source="live")` → 켜진 언어 수만큼 `Translation`(순서 mn, zh) 순으로 나온다.
  2. 군말만 있는 final은 `Final`을 만들지 않는다.
  3. `submit_text`는 `Final(source="text")`, 번역, 그다음 `player.play`가 켜진 언어 수만큼의 클립으로 불린다.
  4. `read_aloud=False`인 실시간 문장은 재생하지 않고, `True`면 재생한다.
  5. router가 `reason="quota"`를 주면 `Status("quota")`는 처음 한 번만 나온다.
  6. 마이크 열기 실패는 `Status("mic_error")`를 내고 `live`가 False다.
  7. 오프라인 모드에서 `speak`는 speaker를 부르지 않는다.
  8. `play_phrase`는 파일이 있으면 `play_files`로 재생한다(tmp 파일).
  9. `set_glossary` 뒤 새 문장에 치환이 적용된다.
  10. `shutdown` 뒤 스레드가 1초 안에 끝난다.
- **커밋:** `feat: 마이크→인식→번역→음성 파이프라인 추가`

### W6: 화면 (메인 창, 번역 전용 창, 패널)

**Files:**
- Create:
  - `src/sukpago/ui/__init__.py`, `src/sukpago/ui/theme.py`, `src/sukpago/ui/layout.py`
  - `src/sukpago/ui/app.py`, `src/sukpago/ui/display.py`, `src/sukpago/ui/panels.py`
  - 테스트: `tests/test_ui_layout.py`, `tests/test_ui_smoke.py`

**할 일**
- **기준:** 설계 문서 3장(기능)과 9장(화면), 그리고 목업 https://claude.ai/artifact/B5Tn8M1U39qwVPppuDEKmY 를 CustomTkinter로 만든다. 목업의 내용은 다음과 같다.
  - 흰 배경
  - 메인 창: 설정 줄, 실시간 듣기, 현재 문장, 패널 3개, 빠른 안내 버튼, 직접 입력, 상태 표시줄
  - 번역 전용 창: 도구 줄, 스크롤되는 전체 기록, 클릭 강조, 글자 크기
- **`theme.py`:** 색(글자 #111318, 보조 #5B6472, 강조 #2563EB, 카드 #F5F7FA, 테두리 #DDE2E9, 초록 #137A45, 주황 #9A5B00, 빨강 #C62828)과 글꼴 선택을 둔다.
  - 글꼴: Windows는 `Malgun Gothic`, `Microsoft YaHei`, `Segoe UI`다. 맥은 `Apple SD Gothic Neo`, `PingFang SC`, `Helvetica Neue`이고, 개발할 때 보기용이다.
- **`layout.py` (순수 함수, 테스트 대상)**
  - `display_sizes(count, size_px, prev_scale, selected) -> list[tuple[int, str, str]]`: 문장마다 (글자 크기, 굵기 "bold"|"normal", 색)을 돌려준다.
    - 최신 문장(또는 선택된 문장): size, bold, 글자색
    - 바로 앞 3문장: round(size × prev_scale), bold, #2A303A
    - 그보다 오래된 문장: round(size × prev_scale × 0.8), normal, 보조색
    - 크기는 최소 18px이다.
  - `clamp_font(px) -> int`: 24~120
  - `step_font(px, delta) -> int`: ±8
  - `PREV_SCALES = {"작게": 0.55, "보통": 0.75, "크게": 0.9}`
  - `status_text(online, engine, reason, mem_mb) -> str`: 예 `"온라인 · 인식 Zipformer · 번역 MyMemory · 메모리 0.6GB"`, 대체 시 `"번역 NLLB (한도 초과)"`
- **`app.py`:** `class App(ctk.CTk)`, `__init__(self, pipeline, settings, phrases_api=phrases, config_api=config)`
  - `after(50)`으로 `pipeline.events`를 꺼내 그린다.
  - 토글·버튼은 pipeline의 set_* 메서드와 연결하고, 바뀐 설정은 `config.save_settings`로 저장한다.
  - `topmost`를 적용하고, 창 위치를 저장·복원한다.
  - 직접 입력이 비었거나 500자를 넘으면 안내한다.
  - 상태 표시줄의 메모리는 psutil로 2초마다 갱신한다.
- **`display.py`:** `class DisplayWindow(ctk.CTkToplevel)`
  - 이벤트는 App이 넘겨준다(`add_final(seq, ko)`, `add_translation(seq, lang, text)`).
  - 기록은 최대 500문장이다.
  - 맨 아래에 있을 때만 자동 스크롤한다.
  - 문장을 클릭하면 강조하고 `pipeline.speak`로 읽는다. [최신 문장으로] 버튼이 있다.
  - 글자 크기는 버튼, 슬라이더, Ctrl+휠로 바꾼다.
  - 이전 문장 크기 3단계, 📌가 있다.
  - 표시는 번역문과 언어 코드만 한다(시간이나 배지는 없음).
  - 여백 8px, 문장 간격 0이다.
- **`panels.py`:** 용어 고치기(추가·삭제 → `config.save_glossary`, `pipeline.set_glossary`)
  - 내 문장 추가: `pipeline.translate_once` → `phrases.add_custom` → 온라인이면 언어별 mp3를 `speaker.synth`로 만들어 `audio_path`에 저장한다. 이 작업은 스레드에서 하고, UI는 `after`로 갱신한다.
  - 마이크 상태: 장치 선택(`mic.list_devices`), 소리 크기 막대, 상태 문구
- **테스트**
  - `test_ui_layout.py`: `display_sizes`, `clamp_font`, `step_font`, `status_text`의 경계값
  - `test_ui_smoke.py`: 화면이 없으면 건너뛴다. 가짜 pipeline으로 App을 만들고, 이벤트 몇 개를 넣고 `update()` 한 뒤 위젯 수와 문구를 확인하고 `destroy()`한다.
- **커밋:** `feat: 화면 배치 계산과 테마 추가`, `feat: 메인 창과 패널 추가`, `feat: 번역 전용 창 추가`

### W7: 조립, 패키징, CI (W1~W6이 합쳐진 뒤)

**Files:**
- Create:
  - `src/sukpago/__main__.py`, `packaging/sukpago.spec`
  - `.github/workflows/ci.yml`, `.github/workflows/release.yml`
  - `THIRD_PARTY_NOTICES.txt`, `README.md`(사용법)

**할 일**
- **`__main__.py`**
  1. `models.ensure("app")`을 부른다. 받을 것이 있으면 Tk 진행 창을 띄운다.
  2. `config.load_settings()`와 `load_glossary()`를 부른다.
  3. `engines.make_router(settings.mymemory_email, paths.models_dir())`를 만든다.
  4. `ZipformerRecognizer`, `CachedSpeaker(EdgeSpeaker())`, `Player()`, `Mic`를 만든다.
  5. 이것들로 `Pipeline`을 만들고 `App(...).mainloop()`를 실행한다.
  6. 종료할 때 `pipeline.shutdown()`을 부른다.
- **`sukpago.spec`:** onedir 빌드로, `customtkinter`의 데이터 파일과 `sherpa_onnx`·`ctranslate2`의 동적 라이브러리를 수집한다. `models/`와 `assets/`는 빌드 후 복사한다(spec에 넣지 않음).
- **CI:** 설계 문서 12장대로 작성한다. 외부 액션은 커밋 SHA로 고정한다.
- **확인**
  - 맥에서 `uv run pytest -q`를 실행한다.
  - `python run.py`로 앱이 뜨고 이벤트가 그려지는지 실제로 확인한다.

**완료 기준:** `uv run pytest -q` 전부 통과. `python run.py` 첫 실행에서 모델 확인부터 앱 실행까지 끝나야 한다.
