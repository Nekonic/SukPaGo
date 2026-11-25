"""배포 전 스모크 테스트: 실제 모델을 올려 인식·번역이 되는지, 최대 메모리가 한도 안인지 본다.

사용: uv run python tools/smoke.py [--max-mb 2048]
"""

from __future__ import annotations

import argparse
import sys

import numpy as np

from sukpago import paths
from sukpago.asr.base import SAMPLE_RATE
from sukpago.quality import is_cyrillic_mongolian, peak_rss_mb


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="석파고 스모크 테스트")
    parser.add_argument("--max-mb", type=float, default=2048)
    args = parser.parse_args(argv)
    m = paths.models_dir()

    from sukpago.asr.zipformer import ZipformerRecognizer

    rec = ZipformerRecognizer(m / "zipformer-ko")
    silence = np.zeros(3 * SAMPLE_RATE, dtype=np.float32)
    for i in range(0, len(silence), SAMPLE_RATE // 10):
        rec.accept(silence[i:i + SAMPLE_RATE // 10])
    rec.finish()
    print("음성 인식: Zipformer 로드와 무음 3초 처리 성공")

    from sukpago.translate.nllb import NllbTranslator

    tr = NllbTranslator(m / "nllb-600m")
    out = {lang: tr.translate("집중하세요.", lang) for lang in ("mn", "zh", "en")}
    print(f"번역: {out}")
    if not is_cyrillic_mongolian(out["mn"]):
        print("실패: 몽골어 결과가 할하 키릴 문자가 아닙니다", file=sys.stderr)
        return 1

    peak = peak_rss_mb()
    print(f"최대 메모리: {peak:.0f}MB (한도 {args.max_mb:.0f}MB)")
    if peak > args.max_mb:
        print("실패: 메모리 한도 초과", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
