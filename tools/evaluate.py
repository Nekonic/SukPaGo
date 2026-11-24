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
        found.append("할하 몽골어 아님")
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
