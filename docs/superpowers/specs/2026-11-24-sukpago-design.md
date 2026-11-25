# 석파고(SukPaGo) 설계

- 작성일: 2026-11-24
- 용도: 학교 파이썬 창작대회 출품작
- 요약: 교수님이 한국어로 말하면 문장 단위로 알아듣고, 몽골어·중국어·영어로 번역해 화면 맨 앞에 크게 띄우는 tkinter 프로그램입니다. 무거운 모델은 리눅스 서버에서 돌리고, 서버에 닿지 않으면 내 컴퓨터의 가벼운 엔진(2GB 이하)으로 자동 전환합니다. `python run.py` 한 줄이면 환경 준비, 모델 받기, 실행까지 끝납니다.

## 1. 목표와 제약

| 항목 | 내용 |
|---|---|
| 클라이언트 | Windows 10/11 64비트의 tkinter(CustomTkinter) 데스크톱 앱. 개발은 맥에서 하지만 판단과 검증은 Windows 기준 |
| 서버 | 리눅스, RAM 8GB, CPU만 씀. Ubuntu Server 26.04 LTS 권장 |
| 실행 | 저장소에서는 `python run.py`(클라이언트)와 `python run.py server`(서버). 배포판은 CI/CD가 만드는 exe zip |
| 파이썬 | uv로 관리. Python 3.13 고정 |
| 비용 | 카드 등록 없음. API 키 없음. 외부 유료 서비스 없음 |
| 메모리 | 서버는 8GB 안(모델 합계 7GB 이하 목표). 클라이언트는 오프라인 엔진을 전부 켜도 2GB 이하 |
| 언어 | 원문은 한국어. 번역은 몽골어(키릴 문자, 할하 방언), 중국어(간체), 영어 |

## 2. 전체 구성

```
교수님 PC: SukPaGo 앱 (tkinter, exe 또는 run.py)
 ├─ [서버 모드] 마이크 PCM ──WebSocket──▶ 리눅스 서버 (FastAPI 프로세스 1개)
 │              ◀── 임시 자막·확정 문장·번역 ──    VAD → Qwen3-ASR (확정 문장)
 │              ── HTTP: 직접 입력 번역, TTS ──▶     Zipformer (임시 자막)
 │                                                 문장 정리 → NLLB-1.3B
 │                                                 sherpa-onnx TTS
 └─ [내 컴퓨터 모드] 앱 안에서 직접: Zipformer → 문장 정리 → NLLB-600M → sherpa-onnx TTS
```

- 서버와 앱은 같은 엔진 코드(`packages/core`)를 씁니다. 엔진을 한 번 고치면 양쪽에 반영되고, 평가 도구도 그대로 씁니다.
- 앱은 두 모드를 토글로 고릅니다: **서버 / 내 컴퓨터**.
  - 서버에 연결할 수 없거나 강의 중 연결이 끊기면, 앱은 내 컴퓨터 모드로 자동 전환합니다.
  - 전환하면 상태 표시줄에 "서버 연결 끊김 · 내 컴퓨터로 번역 중"을 띄웁니다. 토글 상태는 바꾸지 않습니다. 서버가 돌아오면 다음 문장부터 다시 서버를 씁니다.
- 서버 모드에서 앱은 모델을 올리지 않습니다(약 0.1GB). 고정 문장 음성은 앱에 들어 있어서 서버가 없어도 바로 재생됩니다.

## 3. 기능

1. **실시간 강의 번역** (핵심 기능)
   - [🎤 시작] 버튼을 누르면 마이크 입력을 받습니다.
   - 말하는 도중에는 한국어 인식 결과가 회색 "임시 자막"으로 계속 바뀝니다.
   - 교수님이 말을 멈추거나 문장이 끝나면 한국어 문장과 번역이 확정되어 목록에 쌓입니다.
   - 메인 창에는 최신 문장 하나만 크게 보여 줍니다. 지난 문장 전체 기록은 번역 전용 창에서 봅니다.
2. **고정 문장 버튼 5개**: 떠들지 마세요 / 집중하세요 / 이해됐나요? / 질문 있나요? / 질문 없으면 넘어갈게요
   - 미리 검수한 번역(`phrases.json`)과 빌드 때 미리 만든 음성 wav를 씁니다.
   - 모델도 네트워크도 쓰지 않기 때문에 누르는 즉시 뜨고 소리가 납니다.
   - **내 문장 추가**: 선생님이 자주 하는 말을 직접 등록하면 버튼 줄 끝에 "내 문장" 표시와 함께 생깁니다.
     - 번역과 TTS는 추가할 때 한 번만 합니다. 서버 모드면 서버로, 아니면 내 컴퓨터 엔진으로 합니다.
     - 결과는 wav와 함께 사용자 폴더의 `custom_phrases.json`에 저장합니다.
     - 그 뒤로는 고정 문장과 똑같이 바로 뜹니다.
     - 등록된 문장은 목록에서 지울 수 있습니다.
3. **직접 입력 번역**: 한국어 입력창에 쓰고 Enter를 누르면 번역합니다. 마이크가 없을 때나 시연할 때 씁니다.
4. **언어 토글 3개** (몽골어/중국어/영어)
   - 여러 개를 동시에 켤 수 있고, 켜진 언어마다 결과가 한 줄씩 나옵니다.
   - 최소 하나는 켜져 있어야 합니다.
5. **서버 / 내 컴퓨터 토글 1개**: 2장의 규칙대로 동작합니다.
6. **TTS 읽어주기**
   - 고정 문장과 직접 입력 결과는 켜진 언어 순서(몽골어 → 중국어 → 영어)대로 읽습니다.
   - 실시간 강의 모드에서는 기본값이 꺼짐입니다. 교수님 말과 기계 음성이 겹치기 때문입니다. [🔊 실시간 읽기] 토글로 켤 수 있습니다.
   - 결과 줄마다 다시 듣기 버튼이 있습니다.
   - 새 음성이 시작되면 재생 중이던 소리는 멈춥니다.
7. **항상 맨 앞**: 창은 `topmost`로 다른 창 위에 뜹니다. 📌 버튼으로 끄고 켤 수 있고, 기본값은 켜짐입니다.
8. **번역 전용 창**
   - 메인 창의 [번역 창 띄우기] 버튼으로 엽니다. 번역문만 크게 보여 주는 별도 창이라 프로젝터나 두 번째 모니터에 띄우는 용도입니다.
   - 메인 창의 언어 토글을 그대로 따릅니다. 한국어 원문, 버튼, 입력창은 없습니다.
   - **전체 기록**: 이번 실행에서 나온 문장을 모두 보여 줍니다. 오래된 문장이 위, 최신 문장이 아래입니다.
     - 번역문과 언어 코드(MN/ZH/EN)만 표시합니다. 시간, "최신" 같은 배지, 안내 문구는 넣지 않습니다. 글자 자리를 차지하기 때문입니다.
     - 최신 문장은 설정한 글자 크기로 표시합니다.
     - 바로 앞 3문장은 학생이 흐름을 따라올 수 있도록 밝은 글씨로, 최신 문장 크기의 75%(보통)로 표시합니다.
     - 그보다 오래된 문장은 그 80% 크기의 흐린 글씨로 표시합니다.
     - 이전 문장 크기는 도구 줄의 [작게 55% / 보통 75% / 크게 90%]로 바꾸고, `settings.json`에 저장합니다.
     - 화면은 글자에 최대한 내줍니다. 창 가장자리 여백은 8px, 문장 사이 간격은 0, 줄 간격은 1.18로 둡니다. 언어 코드는 글자 앞에 작게 붙이고 따로 칸을 잡지 않습니다. 도구 줄 위아래 여백도 최소로 둡니다.
     - 새 문장이 오면 맨 아래로 자동 스크롤합니다. 사용자가 위로 스크롤해 둔 동안에는 자동 스크롤을 멈춥니다.
   - **문장 클릭**: 그 문장을 최신 문장과 같은 크기로 키우고 테두리로 강조한 뒤, 켜진 언어로 읽어 줍니다.
     - 다시 누르거나 [최신 문장으로] 버튼을 누르면 원래대로 돌아가고 맨 아래로 이동합니다.
   - **글자 크기**: [A−]/[A+] 버튼(8px씩), 슬라이더, `Ctrl` + 마우스 휠로 24~120px 사이에서 바꿉니다. 기본값은 52px입니다.
   - 이 창도 기본으로 맨 앞에 뜨고, 📌 버튼이 따로 있습니다.
   - 글자 크기와 창 위치·크기는 `settings.json`에 저장합니다.
   - 기록은 메모리에만 두고 프로그램을 끄면 사라집니다(최대 500문장).
9. **용어 고치기**: 메인 창에서 "인식된 말 → 바꿀 말"을 등록합니다(예: 노트북 에램 → NotebookLM).
   - 등록 즉시 이후 문장부터 문장 정리 단계에서 치환됩니다. 서버 모드에서는 용어 목록을 서버에 함께 보냅니다.
   - 목록에서 지울 수 있고, 사용자 폴더의 `glossary.json`에 저장합니다.
10. **마이크 상태**: 메인 창에서 마이크를 고르고 입력 소리 크기를 막대로 봅니다.
    - 말하는 구간의 평균 크기가 너무 작거나(−40dBFS 미만) 너무 크면(클리핑 1% 이상) 노란색·빨간색 안내를 띄웁니다.
    - 고른 마이크는 `settings.json`에 저장합니다.

## 4. 엔진

엔진은 공통 인터페이스(`Translator`, `Recognizer`) 뒤에 두고, 역할별로 어떤 엔진을 쓸지는 `assets/engines.json`에서 정합니다.

| 역할 | 서버 (8GB) | 내 컴퓨터 (2GB 이하) |
|---|---|---|
| 확정 문장 음성 인식 | Qwen3-ASR 0.6B int8 + silero VAD (sherpa-onnx `from_qwen3_asr`) | kangkyu 스트리밍 Zipformer chunk-64 int8 |
| 임시 자막 | Zipformer (같은 오디오를 함께 넣음) | Zipformer (확정 문장과 같은 모델) |
| 번역 | NLLB-200 distilled 1.3B CTranslate2 int8 | NLLB-200 distilled 600M CTranslate2 int8 |
| TTS | sherpa-onnx 1.13.8: 몽골어 MMS `mon`, 중국어 Piper `zh_CN-xiao_ya-medium-int8`, 영어 Piper `en_US-amy-medium-int8` | 서버와 같음 |

`engines.json`의 형태는 다음과 같습니다.

```json
{
  "server": {"asr": "qwen3", "partials": "zipformer", "mt": {"mn": "nllb13", "zh": "nllb13", "en": "nllb13"}},
  "client": {"asr": "zipformer", "mt": {"mn": "nllb600", "zh": "nllb600", "en": "nllb600"}}
}
```

몽골어를 바로 번역할지 영어를 거쳐 번역할지(`nllb13` 또는 `nllb13_pivot`)는 몽골어 화자가 평가 결과 10문장을 비교한 뒤 정합니다. 그 전까지는 바로 번역(`nllb13`)을 씁니다.

**평가로 확인한 사실** (2026-11-24, 학생이 녹음한 실제 강의 3개 × 앞 3분, 맥에서 측정)

| 엔진 | 결과 | 최대 메모리 |
|---|---|---|
| Zipformer (띄어쓰기 복원 후) | RTF 0.016, 임시 자막 나옴, 문장부호 없음, 자유 발화 오류 많음 | 500~610MB |
| SenseVoice 2024-07-17 | Zipformer와 비슷한 정확도, 문장부호 있음, 임시 자막 없음 | 920~1040MB |
| Qwen3-ASR 0.6B | 가장 정확하고 문장부호 있음. 핫워드는 효과 없음("NotebookLM" → "오토북 L M") | 2.6~4.1GB |
| NLLB-600M | 몽골어는 할하 키릴로 나오지만 오역이 많음 | 1.26GB |
| NLLB-1.3B | 600M보다 나음. 중국어에서 모르는 한자가 빠짐 | 2.03GB |
| 몽골어 특화 NLLB-1.3B (Tsengel-mn) | 직역이 많고, 영어에서 아포스트로피가 빠짐 | 2.04GB |
| Hy-MT2-1.8B | 몽골어 칸에 러시아어·세르비아어가 나와 **사용 불가** | 2.2GB |
| TranslateGemma-4B | 중국어·영어는 자연스럽지만 없는 내용을 지어내고, CPU에서 느림. **사용 안 함** | 5.2GB |
| Zipformer + NLLB-600M 함께 | 클라이언트 오프라인 조합 | 1690MB |
| Qwen3-ASR + NLLB-1.3B 함께 | 서버 조합 (Zipformer 임시 자막 제외) | 4772MB |

**주의할 점**

- **sherpa-onnx와 sherpa-onnx-core는 1.13.8로 고정합니다.**
  - 2.0.3에서는 Piper 영어 TTS가 실패합니다.
  - 1.13.x에는 한글 사이 공백을 지우는 버그(issue #4128)가 있어서, Zipformer 결과는 토큰을 이어 붙여 띄어쓰기를 복원합니다.
- **MMS 몽골어 TTS는 `ө` 대신 `ѳ`(U+0473)를 씁니다.** 합성 전에 `ө→ѳ`, `Ө→Ѳ`로 바꿉니다.
- **몽골어 판정:** 키릴 문자인지만 보지 않고, 몽골어 고유 글자(ө, ү)가 있는지와 다른 슬라브어 글자(ј, љ, і, є 등)가 없는지도 봅니다(`quality.is_cyrillic_mongolian`).
- **라이선스:** NLLB와 MMS는 CC-BY-NC 4.0(비상업)이라 학교 대회에는 문제없습니다. 배포 zip과 서버 이미지에 `THIRD_PARTY_NOTICES.txt`를 넣습니다.
- **쓰지 않는 것:** MyMemory, edge-tts, Hy-MT2, TranslateGemma 코드는 지웁니다(평가 기록은 git 이력에 남음).

## 5. run.py: 한 줄로 끝까지

`run.py`는 저장소 루트에 있습니다. 표준 라이브러리만 쓰기 때문에 어떤 Python(3.10 이상)으로 실행해도 됩니다.

```
python run.py            # 클라이언트(앱) 실행
python run.py server     # 서버 실행
python run.py setup      # 환경과 모델만 준비하고 실행은 안 함 (client|server|all)
python run.py --server-url ws://192.168.0.10:8765   # 앱이 접속할 서버 지정
```

실행 순서는 다음과 같습니다. 각 단계는 이미 되어 있으면 건너뜁니다.

1. **uv 찾기:** `PATH`에서 찾고, 없으면 `~/.local/bin`(Windows는 `%USERPROFILE%\.local\bin`)을 봅니다. 그래도 없으면 `python -m pip install --user uv`로 설치합니다. pip도 없으면 설치 방법을 출력하고 끝냅니다.
2. **환경 맞추기:** `uv sync --locked --package sukpago-client`(서버는 `sukpago-server`)를 실행합니다. Python 3.13이 없으면 uv가 받아서 설치합니다.
3. **모델 받기:** 역할에 필요한 모델 중 없는 것만 받습니다. 목록은 `tools/models.lock.json`의 `roles`에 있습니다.
   - 받은 뒤 크기와 SHA256을 검증합니다.
   - 검증에 성공하면 파일 옆에 크기·수정 시각 기록을 남기고, 다음 실행부터는 이 기록이 맞으면 해시 계산을 건너뜁니다(1GB 파일을 매번 해시하지 않기 위해서).
   - 받는 동안 파일 이름, 받은 양, 전체 크기를 한 줄로 보여 줍니다.
4. **고정 문장 음성 만들기:** `assets/phrases/*.wav`가 없으면 TTS로 만듭니다(클라이언트만).
5. **실행:** `uv run --package sukpago-client python -m sukpago_client`(서버는 `sukpago_server`)를 실행하고, 종료 코드를 그대로 돌려줍니다.

exe에서는 1~2단계가 필요 없습니다. 앱이 켜질 때 같은 모델 확인 함수(`sukpago_core.models.ensure(role)`)를 부르고, 모델이 빠져 있으면 진행 창을 띄워 exe 옆 `models/`에 받습니다. 보통은 zip에 모델이 들어 있어서 이 과정이 일어나지 않습니다.

## 6. 통신 규약 (`packages/core/sukpago_core/protocol.py`)

서버 주소의 기본값은 `ws://<서버>:8765`이고, 앱 설정에서 바꿉니다.

**접속 확인:** `GET /health` → `{"version": 1, "engines": {...}, "busy": false}`

**실시간 인식:** WebSocket `/ws/live`
- 앱 → 서버
  - 처음에 JSON `{"type": "hello", "version": 1, "token": "...", "langs": ["mn", "zh"], "glossary": [{"wrong": "...", "right": "..."}]}`
  - 그 뒤로 바이너리 프레임: 16kHz 모노 PCM16 리틀엔디언, 100ms(3200바이트)씩
  - 설정이 바뀌면 JSON `{"type": "config", "langs": [...], "glossary": [...]}`
- 서버 → 앱 (JSON)
  - `{"type": "partial", "text": "..."}`
  - `{"type": "final", "seq": 12, "ko": "..."}`
  - `{"type": "translation", "seq": 12, "lang": "mn", "text": "...", "engine": "nllb13"}`
  - `{"type": "error", "code": "busy" | "bad_token" | "version", "message": "..."}`

**한 번만 하는 요청:** HTTP
- `POST /translate` `{"text": "...", "langs": [...]}` → `{"mn": "...", "zh": "..."}`
- `POST /tts` `{"text": "...", "lang": "mn"}` → `audio/wav`

**기타 규칙**
- **토큰:** 서버 환경 변수 `SUKPAGO_TOKEN`을 설정하면 그 값이 맞을 때만 받습니다. 비워 두면 같은 LAN 안에서 누구나 접속할 수 있습니다.
- **동시 접속:** 서버는 실시간 세션을 `SUKPAGO_MAX_SESSIONS`개(기본 1)까지만 받고, 넘으면 `busy`로 거절합니다. 앱은 `busy`를 받으면 내 컴퓨터 모드로 전환합니다.
- **버전:** `version`이 다르면 `version` 오류를 보내고 연결을 끊습니다.
- **메시지 형식:** 모든 메시지는 `protocol.py`의 데이터클래스로 만들고 읽습니다. 서버와 앱이 같은 파일을 씁니다.

## 7. 실시간 파이프라인

```
마이크(miniaudio 캡처, 16kHz 모노)
  → 서버 모드: WebSocket으로 PCM 전송 ─ 서버가 아래 과정을 대신 하고 결과만 돌려줌
  → 내 컴퓨터 모드:
     [음성 인식 스레드] Zipformer 스트리밍 ─ 임시 자막 → UI
                        └ 끝점 감지(말 멈춤) → 문장 조각
     [문장 정리] SentenceAssembler
        · 군말 제거, 짧은 조각 잇기(8자 미만, 최대 3초 대기), 긴 조각 자르기(120자)
        · 용어 사전 치환, 말 더듬기와 반복 단어 정리
     [번역 스레드] 켜진 언어마다 번역(확정 문장만)
     → UI 확정 줄 추가 (+ 실시간 읽기가 켜져 있으면 TTS 큐)
```

서버 안에서는 같은 과정을 거치되, 확정 문장은 Qwen3-ASR(VAD 구간 15초 이하)로 인식하고 임시 자막만 Zipformer로 만듭니다.

- **스레드:** 서버는 FastAPI(uvicorn 워커 1개) 프로세스 하나에 모델을 한 번씩만 올리고, 추론은 스레드 풀에서 돌립니다. onnxruntime과 CTranslate2는 추론 중 GIL을 놓습니다.
  - 스레드 배분(4코어 기준): 음성 인식 2, 번역 2, TTS 1
- **반복 방지(NLLB):** `no_repeat_ngram_size=3`, `repetition_penalty=1.2`, `max_decoding_length = 입력 토큰 × 2 + 16`
- **목표 지연:** 말을 멈추고 확정 번역이 뜰 때까지 서버 모드 2초, 내 컴퓨터 모드 2초 이내
- **마이크 권장:** 교수님 가까이에 두는 핀마이크나 USB 마이크. README에 적습니다.

## 8. 메모리 예산

**서버 (8GB)**

| 구성 | 목표 | 근거 |
|---|---|---|
| OS와 Docker | 1GB | Ubuntu Server 최소 설치 + dockerd |
| Qwen3-ASR | 4GB 이하 | 실측 2.6~4.1GB. VAD 구간 길이를 15초로 제한 |
| Zipformer (임시 자막) | 0.6GB | 실측 500~610MB |
| NLLB-1.3B | 2.1GB | 실측 2.03GB |
| TTS 3종 | 0.45GB | 실측 약 440MB |
| 합계 | 약 8.1GB 이하 | 빠듯함 |

빠듯하기 때문에 다음 규칙을 둡니다.
- **임시 자막 끄기:** 실제 서버에서 최대 메모리가 7GB를 넘으면 `engines.json`에서 서버의 `partials`를 `null`로 바꿔 Zipformer를 끕니다. 그러면 서버 모드에서는 임시 자막 없이 확정 문장만 나옵니다.
- **메모리 상한:** 컨테이너에 `mem_limit: 7g`을 걸고, 호스트에 스왑 4GB와 zram을 둡니다. 메모리가 넘쳐도 OS가 아니라 서비스만 재시작됩니다.
- **glibc 설정:** `MALLOC_ARENA_MAX=2`로 스레드별 메모리 조각화를 줄입니다.

**클라이언트 (2GB 이하)**
- 서버 모드: 모델 없음, 약 0.1GB
- 내 컴퓨터 모드: Zipformer + NLLB-600M 실측 1690MB + TTS(켜진 언어만, 60초 안 쓰면 내림)
- 모델은 처음 쓸 때 올립니다. 서버 모드로 시작하면 자동 전환이 일어날 때까지 올리지 않습니다.
- 상태 표시줄에 현재 메모리(psutil)를 보여 줍니다.

## 9. 저장소 구조 (uv workspace, 저장소 하나)

```
SukPaGo/
├─ run.py                       # 한 줄 실행 (표준 라이브러리만)
├─ pyproject.toml               # workspace 루트: members = ["packages/*"], Python 3.13
├─ uv.lock, .python-version
├─ packages/
│  ├─ core/sukpago_core/        # 서버와 앱이 같이 쓰는 엔진
│  │  ├─ languages.py, paths.py, quality.py, engines.py, models.py(ensure), protocol.py
│  │  ├─ asr/ base.py, vad.py, zipformer.py, sensevoice.py, qwen3.py
│  │  ├─ text/ assembler.py, glossary.py
│  │  ├─ translate/ base.py, nllb.py, pivot.py, router.py
│  │  └─ tts/ base.py, sherpa.py
│  ├─ server/sukpago_server/     # FastAPI: /health, /ws/live, /translate, /tts, 세션 관리
│  └─ client/sukpago_client/     # tkinter 앱
│     ├─ __main__.py, config.py, phrases.py, audio.py, mic.py
│     ├─ remote.py              # 서버 연결 (WebSocket·HTTP, 끊기면 알림)
│     ├─ pipeline.py            # 서버/내 컴퓨터 모드 전환, 스레드와 큐
│     └─ ui/ app.py, display.py
├─ assets/ phrases.json, engines.json, phrases/*.wav(생성물, gitignore)
├─ tools/ download_models.py, models.lock.json, evaluate.py, build_phrase_audio.py
├─ docker/ Dockerfile.server, compose.yaml, Caddyfile(인터넷에 공개할 때만)
├─ packaging/sukpago.spec       # PyInstaller onedir
├─ tests/                       # core, server, client, run.py 테스트
└─ .github/workflows/ ci.yml, client-release.yml, server-image.yml
```

- **의존성:**
  - core: numpy, ctranslate2, sentencepiece, sherpa-onnx(+core) 1.13.8, psutil
  - server: core + fastapi, uvicorn
  - client: core + customtkinter, miniaudio, websockets
  - llama-cpp-python은 쓰지 않으므로 뺍니다.
- **경계 규칙:**
  - UI는 `pipeline`만 호출합니다.
  - `pipeline`은 서버 모드에서 `remote`를, 내 컴퓨터 모드에서 core 엔진을 씁니다.
  - 서버와 앱은 `protocol.py`로만 대화합니다.
  - 모든 엔진은 프로토콜로 정의하고, 테스트는 가짜 엔진으로 돌립니다.
- **현재 코드에서 옮기는 것:** 지금 `src/sukpago/`의 엔진 코드는 `packages/core/sukpago_core/`로 옮깁니다.

## 10. 화면

```
┌ 석파고 SukPaGo ─────────────────────────────── [📌] ┐
│ [● 서버 / ○ 내 컴퓨터] [몽골어✔][중국어✔][영어□]  [🔊 실시간 읽기 □] │
│ [🎤 시작]  임시 자막: 오늘은 광합성에 대해서 배워볼…                  │
│ ───────────────────────────────────────────────────── │
│ KO  다음 주 화요일까지 숙제 꼭 내세요.                         [🔊] │
│ MN  Ирэх долоо хоногийн мягмар гараг хүртэл ...           [🔊] │
│ ZH  请在下周二之前提交作业。                                 [🔊] │
│ ───────────────────────────────────────────────────── │
│ [용어 고치기]  [내 문장 추가]  [마이크 상태]                          │
│ [떠들지 마세요][집중하세요][이해됐나요?][질문 있나요?][질문 없으면 넘어갈게요] │
│ [한국어 직접 입력 ______________________________] [번역]          │
│ 상태: 서버 192.168.0.10 연결됨 · 인식 Qwen3-ASR · 번역 NLLB-1.3B · 메모리 0.1GB │
└──────────────────────────────────────────────────────┘
```

- 화면 목업: https://claude.ai/artifact/B5Tn8M1U39qwVPppuDEKmY (메인 화면과 번역 전용 창)
  - 목업의 "온라인/오프라인"은 "서버/내 컴퓨터"로 바뀝니다.
- 메인 창 헤더에 [번역 창 띄우기] 버튼이 있습니다.
- 메인 창은 위에서부터 다음 순서입니다: 설정 줄, 실시간 듣기, 현재 문장, [용어 고치기 | 내 문장 추가 | 마이크 상태] 패널 3개, 빠른 안내 버튼, 직접 입력, 상태 표시줄.
- 두 창 모두 흰 배경의 밝은 테마입니다. 교수님들이 다크 모드를 싫어하기 때문이고, 다크 모드는 제공하지 않습니다.
  - 글자는 거의 검정(#111318), 강조는 파랑(#2563EB)입니다.
  - 보조 글자도 흰 배경에서 대비 4.5:1 이상인 색을 씁니다.
- 번역 전용 창은 위쪽 도구 줄에 글자 크기 조절과 📌가 있고, 아래는 스크롤되는 전체 기록입니다.
- 메인 창의 현재 문장 번역은 28pt로 표시합니다.
- 글꼴은 Windows 기본 글꼴을 씁니다: 한국어 `Malgun Gothic`, 중국어 `Microsoft YaHei`, 몽골어·영어 `Segoe UI`.
- 상태 표시줄에는 다음을 보여 줍니다.
  - 지금 쓰는 모드와 서버 주소, 연결 상태
  - 인식·번역 엔진 이름
  - 앱의 메모리 사용량

## 11. 오류 처리

| 상황 | 동작 |
|---|---|
| 서버 연결 실패, 강의 중 끊김, `busy` 응답 | 내 컴퓨터 모드로 자동 전환하고 상태 표시줄에 알림. 10초마다 다시 접속을 시도하고, 성공하면 다음 문장부터 서버 사용 |
| 서버 번역·TTS 요청 실패(타임아웃 5초) | 그 요청만 내 컴퓨터 엔진으로 처리 |
| `bad_token`, `version` 오류 | 자동 전환하고 "서버 설정 확인" 안내 (재시도하지 않음) |
| 마이크 없음 또는 열기 실패 | [🎤 시작]을 비활성화하고 안내. 나머지 기능은 계속 동작 |
| 모델 파일 없음 | `models.ensure()`가 받기를 시도. 네트워크가 없으면 해당 기능만 비활성화하고 안내 |
| 번역이 밀림 (큐에 3개 이상) | 상태 표시줄에 "번역 지연" 표시. 확정 문장은 버리지 않음 |
| 직접 입력이 비었거나 500자 초과 | 번역하지 않고 안내 |
| 재생 장치 없음 | 소리 없이 화면에만 표시하고 알림 |
| 서버 메모리 초과로 재시작 | Docker가 자동으로 다시 띄움. 그동안 앱은 내 컴퓨터 모드 |

## 12. 고정 문장 초안

몽골어는 초안입니다. **대회 전에 몽골어 화자에게 검수받습니다.**

| 한국어 | 몽골어 (초안) | 중국어 | 영어 |
|---|---|---|---|
| 떠들지 마세요. | Дуу чимээ гаргахгүй бай. | 请不要大声说话。 | Please be quiet. |
| 집중하세요. | Анхаарлаа төвлөрүүл. | 请集中注意力。 | Please focus. |
| 이해됐나요? | Ойлгов уу? | 听懂了吗？ | Do you understand? |
| 질문 있나요? | Таны асуух зүйл байна уу? | 有问题吗？ | Any questions? |
| 질문 없으면 넘어갈게요. | Хэрэв асуулт байхгүй бол дараагийнх руу шилжицгээе. | 如果没有问题，我们就继续。 | If there are no questions, let's move on. |

고정 문장의 음성은 TTS로 wav를 미리 만듭니다(`assets/phrases/*.wav`).
- exe zip에는 빌드할 때 넣습니다.
- `run.py`로 실행하면 처음 실행할 때 만듭니다.

## 13. 서버 운영

- **OS:** Ubuntu Server 26.04 LTS(2031년까지 지원). 아주 약한 PC면 Debian 13.
  - 둘 다 시스템 Python 대신 uv가 받은 Python 3.13을 씁니다.
  - 시간대는 `Asia/Seoul`, 로캘은 `C.UTF-8`, `PYTHONUTF8=1`로 둡니다.
- **실행 방법 1, Docker Compose (기본):**
  - 실행 명령은 `docker compose up -d`입니다.
  - 모델 폴더는 이미지에 넣지 않고 `/srv/sukpago/models`를 읽기 전용으로 연결합니다.
  - 컨테이너 시작 시 `models.ensure("server")`가 빠진 모델을 받습니다.
  - `restart: unless-stopped`, `mem_limit: 7g`, 로그 크기 제한을 둡니다.
- **실행 방법 2, 저장소에서 바로:** `python run.py server`. systemd 서비스로 등록하는 예시를 README에 둡니다.
- **네트워크:**
  - 학교·집 LAN에서는 `ws://`로 바로 접속합니다. 앱은 브라우저가 아니라서 HTTPS가 없어도 마이크를 쓸 수 있습니다.
  - 열 포트는 8765(앱)와 22(SSH, 키 로그인만)입니다. Docker가 연 포트는 ufw 규칙을 우회하므로, 공유기 밖으로는 포워딩하지 않습니다.
  - 밖에서 접속해야 하면 Tailscale을 쓰고, 필요하면 Caddy로 `wss://`를 붙입니다.
- **서버 위치:** 카드 없이 쓸 수 있는 8GB 무료 클라우드가 없습니다(Oracle은 카드 필수, Hugging Face Docker Space는 유료). 그래서 집이나 학교의 남는 PC를 씁니다. 대회 현장에서는 노트북이나 PC를 같은 LAN에 두는 것이 가장 안정적입니다.
- **구형 CPU:**
  - CTranslate2와 onnxruntime은 AVX2가 없어도 동작합니다(onnxruntime은 실제 PC에서 확인 필요).
  - Rocky 10과 Ubuntu `amd64v3` 변형은 AVX2가 필요하므로 쓰지 않습니다.

## 14. CI/CD (GitHub Actions)

외부 액션은 커밋 SHA로 고정합니다. 워크플로는 세 개입니다.

**`ci.yml`** (`pull_request`와 `main` 푸시)
- `ubuntu-latest`와 `windows-latest`에서 `astral-sh/setup-uv`, `uv sync --locked`, `uv run pytest`를 실행합니다.
- 모델과 네트워크 없이 가짜 엔진으로 돌립니다.

**`client-release.yml`** (태그 `v*` 또는 `workflow_dispatch`, `windows-latest`)
1. `models/`를 `tools/models.lock.json` 해시 키로 캐시하고, `python run.py setup client`로 환경과 클라이언트 모델을 준비합니다. run.py 자체도 이 단계에서 검증됩니다.
2. 스모크 테스트를 실행합니다.
   - 공개 테스트 음성 10초 인식, 번역 1문장, 언어별 TTS 1문장을 돌립니다.
   - 최대 메모리가 2GB를 넘으면 실패 처리합니다.
3. `pyinstaller packaging/sukpago.spec`로 onedir 빌드를 합니다.
4. `dist/SukPaGo/`에 다음을 넣습니다.
   - `models/` (Zipformer, NLLB-600M, VAD, TTS)
   - `assets/` (고정 문장 wav 포함)
   - `THIRD_PARTY_NOTICES.txt`
   - `README.txt` (사용법, 서버 주소 설정, 마이크 권장)
5. `SukPaGo-<버전>-win64.zip`으로 묶습니다. 예상 크기는 약 1.2GB이고, 2GB를 넘으면 실패 처리합니다.
6. Actions 결과물로 올리고, 태그 빌드는 Release에 첨부합니다.

**`server-image.yml`** (태그 `v*`, 그리고 `packages/server/**`·`packages/core/**`·`docker/**`·`uv.lock`이 바뀐 `main` 푸시, `ubuntu-latest`)
1. `docker/Dockerfile.server`로 이미지를 빌드합니다. uv 공식 Docker 방식을 따르고, 모델은 넣지 않습니다.
2. 컨테이너를 띄우고 `/health`가 응답하는지 확인합니다(모델 없이 시작하는 점검 모드).
3. 태그 빌드는 `ghcr.io/<owner>/sukpago-server:<버전>`으로 올립니다(공개 저장소는 GHCR 무료, `GITHUB_TOKEN` 사용).

## 15. 테스트

- **단위 테스트 (pytest, 가짜 엔진)**
  - 기존 core 테스트(언어 표, 용어, 문장 정리, 번역 라우터, 음성 인식 공통 부분, 품질 검사, 모델 받기)
  - `protocol`: 메시지 만들기와 읽기, 버전 불일치
  - `run.py`: uv 찾기 순서, 역할별 모델 목록, 이미 준비된 단계 건너뛰기 (`subprocess` 호출은 가짜로 바꿔 검사)
  - `models.ensure`: 크기·수정 시각 기록이 맞으면 해시를 건너뛰는지
  - 서버: FastAPI TestClient로 `/health`, `/translate`, `/tts`, `/ws/live`(가짜 인식기가 partial/final/translation을 내는지), 토큰 거절, `busy`
  - 클라이언트: `pipeline` 모드 전환(서버 끊김 → 내 컴퓨터, 복구 → 서버), 설정 저장과 불러오기
- **실제 모델 테스트(`models` 표시):** 모델이 있을 때만 돌고, 없으면 건너뜁니다.
- **평가:** `tools/evaluate.py`로 실제 강의 녹음을 돌립니다. 로컬에서만 실행하고 결과는 커밋하지 않습니다(`eval_data/`, `eval_out*/`).
- **수동 확인**
  - Windows PC: 압축 풀고 실행, `python run.py` 첫 실행(모델 받기부터), 맨 앞 표시, 마이크로 실시간 번역, 서버/내 컴퓨터 전환, 서버를 껐을 때 자동 전환, 소리 재생
  - 리눅스 서버: `docker compose up`, 최대 메모리 측정(`/proc/<pid>/status`의 VmHWM)

## 16. 범위 밖

- 학생→교수님 방향 번역
- 화자 구분
- 요약이나 문장 다시 쓰기
- 브라우저 클라이언트(학생 폰으로 보기)
- 서버 여러 대, GPU 서버
- 설치 프로그램(msi), 자동 업데이트
- 다른 언어 추가

언어는 표에 한 줄만 추가하면 늘릴 수 있는 구조로 둡니다.
