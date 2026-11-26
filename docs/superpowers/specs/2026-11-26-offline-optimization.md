# 오프라인 번역 최적화 종합

## 요약

오프라인 품질과 속도를 올릴 방법을 에이전트 11개가 각자 다른 관점으로 조사하고 실측했습니다. 관점은 다음과 같습니다.

- 문장 나누기
- 번역 설정
- 음성 인식
- 다른 모델
- 용어와 캐시
- 파이썬 실행 환경
- 수치 계산과 스레드
- 메모리
- 지연 구조
- Windows
- 평가 도구

결론은 다섯 가지입니다.

1. **가장 큰 문제는 구조에 있었습니다.** 오프라인 번역은 세 언어를 동시에 번역하는 것처럼 보였지만 실제로는 차례로 돌고 있었습니다. `TranslateRouter._offline`이 잠금을 잡은 채로 번역하기 때문입니다. 세 언어를 `translate_batch` 한 번에 묶으면 번역 시간이 약 절반으로 줄고, 출력은 그대로입니다. 세 에이전트가 따로 측정해 같은 결과를 얻었습니다(162/162, 30/30 동일).
2. **번역이 문장 뒷부분을 빼먹는 문제는 입력 길이 때문입니다.** 음성 인식이 15초마다 단어 중간을 강제로 자르고, 쉬지 않고 이어지는 긴 말을 통째로 번역에 넣기 때문입니다. 한국어 형태소 분석기(kiwipiepy)로 문장을 나누고 문장별로 번역하면 빠진 내용이 되살아납니다.
3. **고유명사는 음성 인식 단계에서 고칠 수 있습니다.** 빔 탐색과 강사 용어 핫워드를 쓰면 NotebookLM과 제미나이가 제대로 인식됩니다. 번역 단계에서는 영문 용어를 보호하면 됩니다.
4. **모델을 바꿔도 큰 개선은 없습니다.** 600M과 1.3B의 점수 차이는 통계적으로 의미가 없었습니다. 중국어 전용 모델(MiLMMT)을 더하면 3GB를 넘습니다.
5. **시간이 가장 많이 드는 곳은 강사가 말을 끝내길 기다리는 구간입니다.** 지연의 약 60%가 여기서 생기고, 번역은 25~30%입니다. 절 단위로 먼저 번역해 덧붙이면 체감 지연이 크게 줄지만, 번역 창 모양이 바뀌므로 먼저 확인이 필요합니다.

측정은 모두 개발용 Mac에서 했습니다. 측정 중 에이전트끼리 CPU를 나눠 써서 절대 지연 값은 잡음이 큽니다. 비교값(배율, 동일 여부, 메모리)만 믿을 만합니다. 실제 Windows 노트북에서 다시 재야 합니다.

## 적용한 것

- **오프라인 묶음 번역:** `NllbTranslator.translate_many`와 `TranslateRouter.translate_offline_many`가 켜진 언어를 `translate_batch` 한 번으로 번역합니다. 온라인(MyMemory)은 지금처럼 언어별로 동시에 요청합니다. 실제 강의로 재 보니 확정 → 3개 언어 표시 중앙값이 0.47~0.55초였습니다(전에는 1~2.4초).
- **말하는 도중 먼저 번역:** `ClauseCommitter`(`src/sukpago/text/clauses.py`)가 임시 자막을 봅니다. 연속 두 번 같은 앞부분 안에서 연결 어미나 종결 어미로 끝난 어절까지 먼저 내보내고, 확정이 오면 나머지만 번역합니다. 화면에는 덧붙이기만 하고 고쳐 쓰지 않습니다. 전에 빠지던 절이 번역됩니다.
- **한 줄 길이:** 줄이 너무 짧게 끊기지 않게 세 가지 규칙을 둡니다. 적용 후 온라인 강의 5분의 한 줄 중앙값은 19자에서 31자가 됐고, 12자 미만 줄은 6개에서 0개가 됐습니다.
  - 먼저 번역하는 기준은 문장 끝(종결 어미) 15자 이상, 절 끝(연결 어미) 35자 이상입니다.
  - 문장이 안 끝난 40자 미만 조각은 다음 조각과 합칩니다. 강사가 계속 말하는 동안에는 기다리는 시간을 다시 셉니다.
  - 20초 강제 끊기로 떨어져 나온 조사("보고서" + "를")는 붙입니다.

- **번역 설정:** 실측을 바탕으로 `repetition_penalty`를 없앴습니다(중국어 문장이 일찍 끝나던 원인). 대신 `length_penalty=1.5`와 `disable_unk=True`를 넣었습니다(빈칸 방지). 빔은 2로 둡니다. 빔 4는 조금 낫지만 지연이 두 배라 쓰지 않습니다.
- **강제 끊김 표시:** 인식기가 20초에서 말하는 도중 끊으면 `forced`로 표시합니다. 마지막 낱말 뒤 무음이 0.5초 미만일 때입니다. 이렇게 끊긴 조각은 다음 첫 어절과 붙이고, 떨어져 나온 조사·"도"·서술격 조사("입니다")도 붙입니다.
- **용어 고치기:** 조각을 합친 뒤 한 번만 고칩니다. 절은 고칠 말이나 이미 바른 말 한가운데서 자르지 않습니다.

## 다음에 할 것 (화면 변화 없음)

| 순서 | 변경 | 효과 (실측) | 비용 | 작업량 |
|---|---|---|---|---|
| 1 | 스레드 배치: ASR `num_threads=1`, 번역 `intra_threads = 물리 코어 − 1`(1~4, 성능이 다른 코어가 섞이면 4를 넘기면 느려짐) | ASR은 1스레드로도 실시간 대비 0.024배로 충분 | 없음 | 작음 |
| 2 | 음성 인식을 `modified_beam_search`(경로 4) + `blank_penalty=1.0` + 핫워드로 | "노트북 엘엠" 0 → 4회, 제미나이 0 → 1, 유료 계정 1 → 2 | +30MB, 처리 비율 0.018 → 0.027 | 작음 |
| 3 | 끝점 rule2 0.6 → 0.8초 (rule3 20초는 적용함) | 짧은 조각 감소 | 확정이 0.2초 늦어짐 | 숫자 1개 |
| 4 | kiwipiepy로 문장 조립: 이어 붙인 뒤 문장으로 나누고, 종결어미가 아니면 다음 조각을 기다림. 60~70자를 넘으면 연결어미에서 나눔 | 끊긴 조각이 합쳐지고, 빠지던 문장이 번역됨(영어 출력 87~152자 → 125~235자) | +약 100~270MB(사전을 끄면 가벼움), 번역 호출이 1.5~2배 | 1~1.5일 |
| 5 | rule3에 걸려 끊긴 경계만 `kiwi.space()`로 다시 붙이기 | 끊긴 4건 모두 수정, 정상 경계 5건 유지 | 거의 없음 | 2~3시간 |
| 6 | 문장 가운데 군말(감탄사 IC: 어, 음, 뭐, 자 …) 지우기 | 56문장에 11건 | 없음 | 2시간 |
| 7 | 영문 용어 보호: 영문 토큰을 자동 검출하고, 번역에서 빠졌으면 `X1` 자리표시자로 다시 번역한 뒤 되돌림 | 용어 보존 600M 8 → 27/30, 1.3B 5 → 28/30 | 빠진 경우만 한 번 더 번역 | 반나절 |
| 8 | Windows 전원 조절 해제(`SetProcessInformation`으로 HighQoS)와 우선순위 ABOVE_NORMAL | PowerPoint 전체 화면 때 앱이 효율 코어로 밀리는 것을 막음 | 없음 | 작음 |
| 9 | 오프라인 모드일 때 시작하자마자 번역 모델 미리 올리기 | 첫 문장 지연(모델 읽기, Defender 검사)을 숨김 | 없음 | 작음 |

용어 고치기에 한글 이름을 영문으로 바꾸는 규칙을 넣으면 8번 효과가 커집니다. 예: 클로드→Claude, 제미나이→Gemini, 노트북 엘엠→NotebookLM. 이 규칙은 기존 화면에서 그대로 넣을 수 있습니다.

## 확인이 필요한 것

- **NLLB-1.3B:** 이 조합으로 Mac 실측 2.98GB라 여유가 없습니다(1.3B + 가벼운 kiwi + 핫워드). Windows x86에서는 Mac에서 보인 첫 호출 증가분(+560MB)이 줄 가능성이 있습니다. Windows에서 `peak_wset`를 재 본 뒤 정합니다. 평가 점수로는 600M과 차이가 없었고, 용어 보존은 낫고 잘림은 더 많았습니다.
- **중국어만 `repetition_penalty=1.0`:** 잘림이 40.8%에서 30.6%로 줄지만, 지어낸 문장과 반복이 조금 생깁니다(1.8%). 번역 설정 에이전트의 결과를 본 뒤 정합니다.

## 하지 않을 것

| 항목 | 이유 |
|---|---|
| 잡음 제거(GTCRN) | 인식을 오히려 나쁘게 함(CER 0.384 → 0.455), 노트북 엘엠 적중 4 → 0 |
| Whisper 계열, SenseVoice 2단계 인식 | 환각("구독과 좋아요"), 메모리·속도 초과 |
| MiLMMT-1B(중국어) 추가 | 600M과 같이 써도 3.55GB 이상. 메모리 측정 중에는 중국어 대신 한국어가 나오는 경우도 있었음 |
| MADLAD-400, Qwen3.5, LMT-60, Hy-MT2, TranslateGemma | 몽골어 실패, 지어냄, 예산 초과 |
| 영어를 거쳐 번역 | 오류가 겹치고, 작은 영→몽 모델이 NLLB보다 낫지 않음 |
| `inter_threads=3`, 언어마다 번역기 따로 | 메모리 +810MB ~ 3.7GB로 3GB 초과 |
| 재번역(임시 자막 미리 번역 후 교체), wait-k, 토큰 스트리밍 | 깜빡임, NLLB 구조와 맞지 않음, beam과 함께 못 씀 |
| 며칠 안의 미세조정 | 한↔몽 데이터가 적고(TED·QED 수만 문장), 인식 잡음 입력은 해결하지 못함 |
| 구어체 → 문어체 규칙 변환 | 좋아진 것 4건, 나빠진 것 2건으로 효과가 섞임 |
| 문장부호 복원 모델 | 한국어 모델이 마땅치 않고, 마침표는 kiwi 종결어미 판정으로 대신 가능 |
| int8_float32, `max_queued_batches`, ISA 환경변수, numpy 경로 최적화 | 측정상 이득 없음(오디오 경로는 µs 단위) |
| Python 3.14, free-threaded 빌드, PyPy, 별도 프로세스 | GIL이 병목이 아님(GIL 대기 p99 1ms, 글루 코드 1% 미만). sherpa-onnx와 ctranslate2에 해당 휠이 없음 |
| `intra_threads` 8 이상 | 성능이 다른 코어가 섞인 CPU에서 오히려 느려짐(Mac 8 → 2.87s, 4 → 1.74s). 상한 4~6 |
| DirectML, timeBeginPeriod | 별도 빌드가 필요하거나, Python 3.11 이상에서 이미 해결됨 |

## 근거

### 지연 구조 (강의 3개, 확정 문장 54개)

| 구간 | 중앙값 |
|---|---|
| 단어 발화 → 한국어 임시 자막 | 1.08s |
| 단어 발화 → 확정 | 5.2s (p90 12.7s) |
| 그중 끝점 대기 | 1.63s |
| 확정 → 3개 언어 표시 | 약 2.6s |
| 단어 발화 → 번역 표시 | 5.6~9.2s (p90 11.7~15.7s) |

음성 인식 계산은 0.1초당 2.6ms라 병목이 아닙니다. 확정 문장 54개 중 10개가 15초 강제 끊기에 걸렸습니다.

### 메모리 (Mac 실측 최대치)

| 조합 | 최대 |
|---|---|
| NLLB-600M (현재) | 1,815MB |
| 600M + 가벼운 kiwi + 핫워드 | 2,489MB |
| NLLB-1.3B | 2,749MB |
| 1.3B + 가벼운 kiwi + 핫워드 | 2,982MB |
| 1.3B + 기본 kiwi + 핫워드 | 3,202MB |
| 600M + kiwi + MiLMMT | 3,552MB 이상 |

현재 600M 구성의 대략적인 내역입니다.
- UI 160MB
- 음성 인식 약 470MB
- 번역 가중치 660MB
- 번역 첫 호출 일회성 약 560MB

가벼운 kiwi는 `Kiwi(load_multi_dict=False, load_typo_dict=False)`입니다.

### 번역 점수 (56문장, MyMemory 번역을 의사 참조로 사용)

| 설정 | mn chrF | zh chrF | en chrF | zh 잘림 |
|---|---|---|---|---|
| 600M | 25.9 | 10.5 | 29.7 | 42.9% |
| 1.3B | 25.4 | 11.5 | 29.3 | 40.8% |
| 1.3B, zh rp=1.0 | | 13.1 | | 30.6% |

차이는 모두 95% 구간 안이라 의미가 없습니다. 의사 참조가 MyMemory라서 MyMemory와 비슷한 엔진이 유리하고, 원문 자체가 인식 오류문입니다. 같은 입력에서 엔진끼리 비교하는 용도로만 씁니다.

### Windows 예상 (추정)

- Windows용 CTranslate2는 Intel CPU에서 MKL, AMD CPU에서 oneDNN을 자동으로 고릅니다. AMD에서 MKL이 느린 문제는 생기지 않습니다.
- AVX2가 없는 CPU(Celeron 등)도 실행은 되지만, 오프라인 번역은 쓸 수 없을 만큼 느릴 것으로 봅니다.
- 일반 i5/Ryzen 5 노트북에서는 Mac보다 1.5~3배 느릴 것으로 봅니다. 묶어서 번역하면 3개 언어에 1~3.5초로 추정합니다. 배터리로 돌리면 1.2~2배 더 느립니다.
- 서명하지 않은 exe는 SmartScreen 경고가 뜹니다. 스마트 앱 컨트롤이 켜진 PC에서는 아예 막힙니다.

## 평가 방법

변경마다 같은 입력으로 비교합니다. 평가 스크립트는 로컬 scratch에 있고 저장소에는 넣지 않았습니다.

- **번역:** chrF/chrF++, 길이 비율, 잘림 비율, 글자체 오류, 반복, 용어 보존, 지연. 두 설정은 paired bootstrap으로 비교합니다.
- **음성 인식:** Whisper large-v3-turbo로 만든 의사 정답과의 CER, 핵심어 재현율, 핫워드 과잉 삽입.
- **함께 확인할 것:** 앱의 `is_cyrillic_mongolian` 판정이 ө/ү가 없는 긴 몽골어 문장과 YouTube 같은 라틴 상표명을 오류로 잡습니다. 1.3B 몽골어 출력의 14.3%가 이렇게 잘못 걸렸습니다.

## 참고

- CTranslate2: [parallel](https://opennmt.net/CTranslate2/parallel.html), [performance](https://opennmt.net/CTranslate2/performance.html), [decoding](https://opennmt.net/CTranslate2/decoding.html), [environment variables](https://opennmt.net/CTranslate2/environment_variables.html)
- [sherpa-onnx endpoint](https://k2-fsa.github.io/sherpa/ncnn/endpoint.html), [sherpa-onnx punctuation models](https://k2-fsa.github.io/sherpa/onnx/punctuation/pretrained_models.html)
- [Windows SetProcessInformation](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-setprocessinformation), [Quality of Service](https://learn.microsoft.com/en-us/windows/win32/procthread/quality-of-service)
- [Arivazhagan et al. 2020, Re-translation versus Streaming](https://aclanthology.org/2020.iwslt-1.27), [Whisper-Streaming (LocalAgreement)](https://arxiv.org/html/2307.14743)
- [MiLMMT 논문](https://arxiv.org/html/2602.11961v1), [MADLAD-400 논문](https://arxiv.org/pdf/2309.04662), [NLLB 논문](https://arxiv.org/pdf/2207.04672)
