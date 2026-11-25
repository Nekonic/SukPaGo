# 석파고(SukPaGo) 설계

- 작성일: 2026-11-24
- 용도: 학교 파이썬 창작대회 출품작
- 요약: 교수님이 한국어로 말하면 문장 단위로 알아듣고, 몽골어·중국어·영어로 번역해 화면 맨 앞에 크게 띄우는 tkinter 프로그램입니다.
  - 음성 인식은 내 컴퓨터에서 합니다.
  - 번역과 음성은 키가 필요 없는 무료 API(MyMemory, edge-tts)를 씁니다.
  - 인터넷이 안 되거나 번역 한도를 넘으면 내 컴퓨터의 NLLB-600M으로 넘어갑니다.
  - `python run.py` 한 줄이면 환경 준비, 모델 받기, 실행까지 끝납니다.

## 1. 목표와 제약

| 항목 | 내용 |
|---|---|
| 실행 환경 | Windows 10/11 64비트의 tkinter(CustomTkinter) 앱. 개발은 맥에서 하지만 판단과 검증은 Windows 기준 |
| 실행 | 저장소에서는 `python run.py`. 배포판은 CI/CD가 만드는 exe zip |
| 파이썬 | uv로 관리. Python 3.13 고정 |
| 비용 | 카드 등록 없음. API 키 없음 |
| 무료 API | 번역 MyMemory (`de=abcd@gmail.com`), 음성 edge-tts |
| 메모리 | 내 컴퓨터 엔진을 전부 켜도 2GB 이하 |
| 언어 | 원문은 한국어. 번역은 몽골어(키릴 문자, 할하 방언), 중국어(간체), 영어 |

## 2. 전체 구성

```
마이크 → [내 컴퓨터] Zipformer 음성 인식 → 문장 정리
       → 번역: MyMemory API ─(실패·한도 초과·오프라인)→ 내 컴퓨터 NLLB-600M
       → 화면 (메인 창, 번역 전용 창)
       → 음성: edge-tts ─(실패·오프라인)→ 소리 없이 화면만
```

## 3. 기능

화면에는 아래 기능만 둡니다. 여기 없는 기능은 넣지 않습니다.

1. **실시간 강의 번역** (핵심 기능)
   - [● 녹음 시작]을 누르면 마이크(기본 장치) 입력을 받습니다. 녹음 중에는 [■ 멈추기]가 됩니다.
   - 말하는 도중에는 한국어 인식 결과가 "임시 자막"으로 계속 바뀝니다.
   - 교수님이 말을 멈추거나 문장이 끝나면 한국어 문장과 번역이 확정됩니다.
   - 메인 창에는 최신 문장 하나만 보여 줍니다. 지난 문장은 번역 전용 창에서 봅니다.
   - 실시간 문장은 소리로 읽지 않습니다. 교수님 말과 기계 음성이 겹치기 때문입니다.
2. **빠른 안내 버튼 5개**: 떠들지 마세요 / 집중하세요 / 이해됐나요? / 질문 있나요? / 질문 없으면 넘어갈게요
   - 누르면 미리 검수한 번역(`phrases.json`)을 바로 띄우고, 미리 만든 음성 mp3를 켜진 언어 순서(몽골어 → 중국어 → 영어)대로 재생합니다.
   - API도 모델도 쓰지 않아서 인터넷이 없어도 동작합니다.
3. **언어 선택 3개** (몽골어/중국어/영어): 여러 개를 동시에 켤 수 있고, 최소 하나는 켜져 있어야 합니다.
4. **온라인/오프라인 선택**: 온라인은 MyMemory, 오프라인은 NLLB-600M입니다. 온라인인데 실패하거나 한도를 넘으면 그 요청만 NLLB로 처리하고 한 줄로 알립니다.
5. **용어 고치기** (메인 창 안): "인식된 말 → 바꿀 말"을 입력해 [추가]합니다. 등록된 규칙은 그 옆에 "노트북 에램 → NotebookLM ✕"로 나열되고, 누르면 지워집니다. 사용자 폴더의 `glossary.json`에 저장합니다.
6. **마이크 소리 막대**: 녹음 버튼 옆의 작은 막대로 소리 크기를 보여 줍니다(초록 적당, 주황 작음, 빨강 너무 큼).
7. **항상 맨 앞**: 메인 창과 번역 전용 창 모두 항상 다른 창 위에 뜹니다. 끄는 버튼은 없습니다.
8. **번역 전용 창**: 메인 창의 [번역 창] 버튼으로 엽니다. 프로젝터나 두 번째 모니터용입니다.
   - 번역문만 보여 줍니다. 한국어 원문, 언어 코드(MN/ZH), 시간, 배지, 안내 문구는 없습니다.
   - 모든 문장을 같은 크기·같은 색(검정, 굵게)으로 보여 주고, 오래된 문장이 위, 최신 문장이 아래입니다.
   - 새 문장이 오면 맨 아래로 따라갑니다. 위로 스크롤해 둔 동안에는 따라가지 않습니다.
   - 도구는 글자 크기 조절 하나뿐입니다: [A−] 슬라이더 [A+] (버튼은 8px씩, 슬라이더는 4px 단위, 24~120px, 기본 52px).
   - 여백 8px, 문장 사이 간격 0입니다. 글자 크기와 창 위치·크기는 `settings.json`에 저장합니다.
   - 기록은 메모리에만 두고 프로그램을 끄면 사라집니다(최대 500문장).
9. **안내 한 줄**: 화면 맨 아래에 오류나 대체 상황이 있을 때만 한 줄 띄웁니다(예: "오프라인으로 전환됨"). 한도 초과 안내는 계속 보이고, 나머지는 다음 문장에서 지워집니다.

## 4. 엔진

| 역할 | 기본 | 대체 |
|---|---|---|
| 음성 인식 | kangkyu 스트리밍 Zipformer chunk-64 int8 (sherpa-onnx, 내 컴퓨터) | – |
| 번역 | MyMemory `api.mymemory.translated.net/get`, `de=abcd@gmail.com` | NLLB-200 distilled 600M CTranslate2 int8 (내 컴퓨터) |
| 음성 | edge-tts: `mn-MN-YesuiNeural`, `zh-CN-XiaoxiaoNeural`, `en-US-JennyNeural` | 없음 (소리 없이 화면만) |

**언어 코드**

| 언어 | MyMemory | NLLB | edge-tts |
|---|---|---|---|
| 한국어 | `ko` | `kor_Hang` | – |
| 몽골어 | `mn` | `khk_Cyrl` | `mn-MN-YesuiNeural` |
| 중국어 | `zh-CN` | `zho_Hans` | `zh-CN-XiaoxiaoNeural` |
| 영어 | `en` | `eng_Latn` | `en-US-JennyNeural` |

**확인한 사실과 주의할 점**

- **MyMemory**
  - 키 없이 ko→mn/zh-CN/en 호출이 성공했고, 몽골어는 키릴 문자로 나왔습니다. 수업 문장은 NLLB보다 훨씬 정확했습니다.
  - 하루 한도는 이메일을 넣으면 50,000자, 안 넣으면 5,000자입니다(IP 기준). 한도는 원문 글자 수 × 번역할 언어 수로 셉니다.
    - 50분 강의(한국어 약 1만 자)를 3개 언어로 번역하면 약 3만 자를 씁니다. 그래서 **하루 강의 1~2개가 한도**입니다.
    - 학교 와이파이처럼 IP를 공유하면 한도도 같이 씁니다.
    - 한도를 넘으면 그날은 NLLB로 넘어갑니다.
  - 이메일 `abcd@gmail.com`은 사용자가 지정한 값입니다. 다른 사람이 같은 주소를 쓰면 한도를 나눠 쓰게 됩니다. `settings.json`에서 바꿀 수 있습니다.
- **edge-tts:** 키 없이 몽골어·중국어 음성 생성에 성공했습니다. 비공식 인터페이스라 언제든 막힐 수 있고, 막히면 소리 없이 화면만 보여 줍니다.
- **Zipformer:**
  - 실제 강의에서 RTF 0.016, 최대 메모리 500~610MB였습니다.
  - sherpa-onnx 1.13.x에는 한글 공백을 지우는 버그(issue #4128)가 있어서, 토큰을 이어 붙여 띄어쓰기를 복원합니다.
  - 문장부호는 없고, 자유 발화에서는 오류가 많습니다.
- **NLLB-600M:** 몽골어는 할하 키릴로 나오지만 오역이 많고, 중국어에서 모르는 한자가 빠집니다. 대체 엔진으로만 씁니다.
- **메모리:** Zipformer + NLLB-600M을 함께 올려 실측 1690MB입니다.
- **sherpa-onnx와 sherpa-onnx-core는 1.13.8로 고정합니다.**
- **라이선스:** NLLB는 CC-BY-NC 4.0(비상업)이라 학교 대회에는 문제없습니다. zip에 `THIRD_PARTY_NOTICES.txt`를 넣습니다.
- **평가 기록:** 평가했지만 쓰지 않는 엔진(Hy-MT2, TranslateGemma, Qwen3-ASR, SenseVoice, NLLB-1.3B)의 결과는 git 이력과 `eval_out*/`(로컬)에 있습니다.
  - Hy-MT2와 TranslateGemma 코드는 지웁니다. llama-cpp-python 의존성을 없애 exe 빌드를 단순하게 하기 위해서입니다.

## 5. run.py: 한 줄로 끝까지

`run.py`는 저장소 루트에 있습니다. 표준 라이브러리만 쓰기 때문에 어떤 Python(3.10 이상)으로 실행해도 됩니다.

```
python run.py          # 앱 실행
python run.py setup    # 환경과 모델만 준비하고 실행은 안 함
```

각 단계는 이미 되어 있으면 건너뜁니다.

1. **uv 찾기:** `PATH`, 그다음 `~/.local/bin`(Windows는 `%USERPROFILE%\.local\bin`)에서 찾습니다. 없으면 `python -m pip install --user uv`로 설치하고, pip도 없으면 설치 방법을 출력하고 끝냅니다.
2. **환경 맞추기:** `uv sync --locked`를 실행합니다. Python 3.13이 없으면 uv가 받습니다.
3. **모델 받기:** `tools/models.lock.json`의 `roles.app` 목록(Zipformer, NLLB-600M) 중 없는 것만 받고, 크기와 SHA256을 검증합니다.
   - 검증한 파일 옆에 크기·수정 시각 기록을 남깁니다. 다음 실행부터는 이 기록이 맞으면 해시 계산을 건너뜁니다.
4. **고정 문장 음성:** `assets/phrases/*.mp3`가 없으면 edge-tts로 만듭니다. 인터넷이 없으면 경고만 하고 넘어갑니다.
5. **실행:** `uv run python -m sukpago`를 실행하고, 종료 코드를 그대로 돌려줍니다.

exe에서는 1~2단계가 필요 없습니다. 앱이 켜질 때 `sukpago.models.ensure()`를 불러, 모델이 빠져 있으면 진행 창을 띄우고 exe 옆 `models/`에 받습니다. 보통은 zip에 모델이 들어 있어서 이 과정이 일어나지 않습니다.

## 6. 실시간 파이프라인

```
마이크(miniaudio 캡처, 16kHz 모노 float32)
  → [음성 인식 스레드] Zipformer 스트리밍 ─ 임시 자막 → UI
                       └ 끝점 감지(말 멈춤) → 문장 조각
  → [문장 정리] SentenceAssembler
       · 군말 제거, 짧은 조각 잇기(8자 미만, 최대 3초 대기), 긴 조각 자르기(120자)
       · 용어 사전 치환, 말 더듬기와 반복 단어 정리
  → [번역 스레드] 켜진 언어마다 번역 (확정 문장만, 들어온 순서대로)
  → UI 확정 줄 추가 (실시간 문장은 읽지 않음. 음성 스레드는 빠른 안내 버튼 재생만 맡음)
```

- **UI로 넘기기:** 각 스레드는 `queue.Queue`로 일을 받습니다. UI에 보낼 결과는 이벤트 큐에 넣고, Tk가 `after(50ms)`로 꺼내 그립니다. UI는 막히지 않습니다.
- **반복 방지(NLLB):** `no_repeat_ngram_size=3`, `repetition_penalty=1.2`, `max_decoding_length = 입력 토큰 × 2 + 16`
- **목표 지연:** 말을 멈추고 확정 번역이 뜰 때까지 2초 이내. MyMemory 응답은 문장·언어당 약 0.3~1초입니다.
- **음성 캐시:** 같은 (문장, 언어)의 mp3는 다시 만들지 않습니다. 실행 중에는 메모리 캐시를 쓰고, 최대 200개까지 둡니다.
- **마이크 권장:** 교수님 가까이에 두는 핀마이크나 USB 마이크. README에 적습니다.

## 7. 메모리 (2GB 이하)

| 구성 | 실측·추정 |
|---|---|
| UI와 파이썬 | 약 80MB (추정) |
| Zipformer | 500~610MB |
| NLLB-600M | 약 1.2GB, 처음 대체가 필요할 때만 올림 |

- 온라인 모드에서는 NLLB를 올리지 않습니다. 대체가 처음 필요한 순간에 올리고, 10분 동안 안 쓰면 내립니다.
- 상태 표시줄에 현재 메모리(psutil)를 보여 줍니다.

## 8. 구조

```
SukPaGo/
├─ run.py                      # 한 줄 실행 (표준 라이브러리만)
├─ pyproject.toml, uv.lock, .python-version (3.13)
├─ src/sukpago/
│  ├─ __main__.py              # models.ensure() → UI 실행
│  ├─ languages.py, paths.py, quality.py
│  ├─ config.py                # settings.json (모드, 언어, 이메일, 맨 앞, 창 위치, 글자 크기, 마이크)
│  ├─ userdata.py              # 사용자 폴더: settings.json, glossary.json
│  ├─ phrases.py               # 빠른 안내 문장 5개와 음성 파일 위치
│  ├─ models.py                # ensure(): 모델 확인·받기 (tools/download_models.py와 같은 코드)
│  ├─ engines.py               # 엔진 생성, ModelManager
│  ├─ asr/ base.py, zipformer.py, mic.py(miniaudio 캡처, 소리 크기 계산)
│  ├─ text/ assembler.py, glossary.py
│  ├─ translate/ base.py, mymemory.py, nllb.py, router.py
│  ├─ tts/ base.py, edge.py(edge-tts → mp3), cache.py
│  ├─ audio.py                 # mp3/wav 재생과 정지 (miniaudio, 한 번에 하나)
│  ├─ pipeline.py              # 스레드와 큐, 이벤트를 UI로
│  └─ ui/ theme.py, layout.py(계산), app.py(메인 창, 용어 고치기·마이크 막대 포함), display.py(번역 전용 창)
├─ assets/ phrases.json, phrases/*.mp3(생성물, gitignore)
├─ tools/ download_models.py, models.lock.json, evaluate.py, build_phrase_audio.py
├─ packaging/sukpago.spec      # PyInstaller onedir
├─ tests/
└─ .github/workflows/ ci.yml, release.yml
```

- **의존성:** numpy, ctranslate2, sentencepiece, sherpa-onnx(+core) 1.13.8, psutil, customtkinter, miniaudio, edge-tts (개발용: pytest, pyinstaller)
- **사용자 폴더:** Windows는 `%APPDATA%\SukPaGo`, 그 밖은 `~/.sukpago`입니다. 테스트에서는 환경 변수 `SUKPAGO_HOME`으로 바꿉니다.
- **경계 규칙**
  - UI는 `pipeline`과 `phrases`, `config`만 호출합니다.
  - 엔진은 프로토콜 뒤에 두고 `engines.py`가 만듭니다.
  - 테스트는 가짜 엔진으로 돌립니다.

## 9. 화면

```
┌ 석파고 SukPaGo ──────────────────────────────────────────┐
│ [온라인|오프라인]  ☑몽골어 ☑중국어 ☐영어                [번역 창] │
│ [● 녹음 시작] ▬▬▬▭▭  오늘은 광합성에 대해서 배워볼…               │
│ 다음 주 화요일까지 숙제 꼭 내세요.                                │
│ Ирэх долоо хоногийн мягмар гараг хүртэл …  (크게, 굵게)          │
│ 请在下周二之前提交作业。                                          │
│ [떠들지 마세요][집중하세요][이해됐나요?][질문 있나요?][질문 없으면 넘어갈게요] │
│ 용어 고치기 [인식된 말]→[바꿀 말][추가]  노트북 에램 → NotebookLM ✕   │
│ (안내가 있을 때만) 오프라인으로 전환됨                              │
└──────────────────────────────────────────────────────────┘
```

- 흰 배경 테마 하나만 둡니다(다크 모드 없음). 글자는 #111318, 강조는 파랑 #2563EB, 녹음 버튼은 빨강 #C62828입니다.
- 이모지 아이콘은 쓰지 않습니다.
- 글꼴은 Windows 기본 글꼴입니다: 한국어 `Malgun Gothic`, 중국어 `Microsoft YaHei`, 몽골어·영어 `Segoe UI`.
- 화면 목업: https://claude.ai/artifact/B5Tn8M1U39qwVPppuDEKmY

## 10. 오류 처리

| 상황 | 동작 |
|---|---|
| MyMemory 실패(타임아웃 5초, HTTP 오류) | 그 요청만 NLLB로 처리하고 상태 표시줄에 알림 |
| MyMemory 한도 초과(`quotaFinished`, 429) | 앱을 끌 때까지 NLLB를 쓰고 상태 표시줄에 "오늘 번역 한도 초과"를 표시 |
| edge-tts 실패 | 소리 없이 화면만 보여 주고 알림 |
| 마이크 없음 또는 열기 실패 | 녹음 버튼을 원래대로 돌리고 안내 한 줄. 나머지 기능은 계속 동작 |
| 모델 파일 없음 | `models.ensure()`가 받기를 시도. 네트워크가 없으면 해당 기능만 비활성화하고 안내 |
| 번역이 밀림 (큐에 3개 이상) | 상태 표시줄에 "번역 지연" 표시. 확정 문장은 버리지 않음 |
| 재생 장치 없음 | 소리 없이 화면에만 표시하고 알림 |

## 11. 고정 문장 초안

몽골어는 MyMemory 결과를 그대로 넣은 초안입니다. **대회 전에 몽골어 화자에게 검수받습니다.**

| 한국어 | 몽골어 (초안) | 중국어 | 영어 |
|---|---|---|---|
| 떠들지 마세요. | Дуу чимээ гаргахгүй бай. | 请不要大声说话。 | Please be quiet. |
| 집중하세요. | Анхаарлаа төвлөрүүл. | 请集中注意力。 | Please focus. |
| 이해됐나요? | Ойлгов уу? | 听懂了吗？ | Do you understand? |
| 질문 있나요? | Таны асуух зүйл байна уу? | 有问题吗？ | Any questions? |
| 질문 없으면 넘어갈게요. | Хэрэв асуулт байхгүй бол дараагийнх руу шилжицгээе. | 如果没有问题，我们就继续。 | If there are no questions, let's move on. |

음성 mp3는 edge-tts로 `assets/phrases/<번호>_<언어>.mp3`에 미리 만듭니다.
- exe zip에는 빌드할 때 넣습니다.
- `run.py`는 처음 실행할 때 만듭니다.

## 12. CI/CD (GitHub Actions)

외부 액션은 커밋 SHA로 고정합니다.

**`ci.yml`** (`pull_request`와 `main` 푸시)
- `windows-latest`와 `ubuntu-latest`에서 `astral-sh/setup-uv`, `uv sync --locked`, `uv run pytest`를 실행합니다.
- 모델과 네트워크 없이 가짜 엔진으로 돌립니다.

**`release.yml`** (태그 `v*` 또는 `workflow_dispatch`, `windows-latest`)
1. `models/`를 `tools/models.lock.json` 해시 키로 캐시합니다.
2. `python run.py setup`으로 환경, 모델, 고정 문장 mp3를 준비합니다. run.py도 이 단계에서 함께 검증됩니다.
3. 스모크 테스트를 실행합니다.
   - Zipformer로 공개 테스트 음성(`models/` 안의 `test_wavs`) 인식
   - NLLB로 1문장 번역
   - 최대 메모리가 2GB를 넘으면 실패 처리
4. `uv run pyinstaller packaging/sukpago.spec`로 onedir 빌드를 합니다.
5. `dist/SukPaGo/`에 다음을 넣습니다.
   - `models/` (Zipformer, NLLB-600M)
   - `assets/` (고정 문장 mp3 포함)
   - `THIRD_PARTY_NOTICES.txt`
   - `README.txt` (사용법, 마이크 권장, MyMemory 한도 안내)
6. `SukPaGo-<버전>-win64.zip`으로 묶습니다. 예상 크기는 약 1GB이고, 2GB를 넘으면 실패 처리합니다.
7. Actions 결과물로 올리고, 태그 빌드는 Release에 첨부합니다.

## 13. 테스트

- **단위 테스트(pytest, 가짜 엔진)**
  - 기존 테스트(언어 표, 용어, 문장 정리, MyMemory, NLLB, 라우터, 음성 인식 공통 부분, 품질 검사, 모델 받기)
  - 설정·사용자 폴더 저장과 불러오기, 빠른 안내 문장 5개
  - 마이크 소리 크기 계산(dBFS, 클리핑 비율)
  - edge-tts 래퍼: 언어별 음성 이름, 캐시
  - 라우터: 한도 초과 뒤 계속 NLLB를 쓰는지
  - 파이프라인: 가짜 인식기·번역기로 partial → final → translation 이벤트 순서, 실시간 문장은 읽지 않는지, 마이크 소리 크기 이벤트
  - 화면 계산(글자 크기 단계, 켜진 언어 순서, 소리 막대 길이)과 화면 연기 테스트(가짜 파이프라인으로 이벤트 그리기, 용어 추가·삭제)
  - run.py: uv 찾기 순서, 준비된 단계 건너뛰기 (`subprocess`는 가짜로 바꿔 검사)
- **실제 모델 테스트(`models` 표시):** 모델이 있을 때만 돌고, 없으면 건너뜁니다.
- **수동 확인 (Windows PC)**
  - `python run.py` 첫 실행(모델 받기부터)
  - exe zip 압축 풀고 실행
  - 맨 앞 표시, 번역 전용 창
  - 마이크로 실시간 번역
  - 인터넷을 끊었을 때 NLLB로 넘어가는지
  - 소리 재생
  - 작업 관리자에서 메모리 확인

## 14. 범위 밖

- 서버와 브라우저 클라이언트
- 학생→교수님 방향 번역
- 화자 구분
- 요약이나 문장 다시 쓰기
- 설치 프로그램(msi), 자동 업데이트
- 다른 언어 추가

언어는 표에 한 줄만 추가하면 늘릴 수 있는 구조로 둡니다.
