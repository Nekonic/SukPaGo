"""assets/phrases.json의 고정 문장을 언어별 mp3로 만들어 assets/phrases/에 둔다.

이미 있는 파일은 건너뛴다. 인터넷이 안 되면 경고만 하고 종료 코드 0으로 끝난다.

사용: uv run python tools/build_phrase_audio.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from sukpago import paths
from sukpago.languages import TARGET_ORDER
from sukpago.tts.base import Speaker, TtsError


def main(speaker: Speaker | None = None, phrases_file: Path | None = None,
         out_dir: Path | None = None) -> int:
    phrases_file = Path(phrases_file) if phrases_file else paths.assets_dir() / "phrases.json"
    out_dir = Path(out_dir) if out_dir else paths.assets_dir() / "phrases"
    try:
        phrases = json.loads(phrases_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"오류: {phrases_file}를 읽을 수 없음: {e}", file=sys.stderr)
        return 1
    if speaker is None:
        from sukpago.tts.edge import EdgeSpeaker

        speaker = EdgeSpeaker()

    out_dir.mkdir(parents=True, exist_ok=True)
    made = skipped = 0
    for phrase in phrases:
        for lang in TARGET_ORDER:
            target = out_dir / f"{phrase['key']}_{lang}.mp3"
            if target.exists() and target.stat().st_size > 0:
                skipped += 1
                continue
            text = phrase.get(lang)
            if not text:
                print(f"경고: {phrase['key']}에 {lang} 번역이 없어 건너뜀", file=sys.stderr)
                continue
            try:
                audio = speaker.synth(text, lang)
            except TtsError as e:
                # 대개 인터넷 문제라 나머지도 실패한다. 다음 실행에서 이어서 만든다.
                print(f"경고: 음성 생성 실패({target.name}): {e}. 인터넷 연결 뒤 다시 실행하세요.",
                      file=sys.stderr)
                print(f"만듦 {made}개, 건너뜀 {skipped}개")
                return 0
            tmp = target.with_name(target.name + ".tmp")
            tmp.write_bytes(audio)
            os.replace(tmp, target)
            made += 1
            print(f"만듦: {target.name}")
    print(f"만듦 {made}개, 건너뜀 {skipped}개")
    return 0


if __name__ == "__main__":
    sys.exit(main())
