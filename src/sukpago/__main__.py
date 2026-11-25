"""석파고 실행: 모델 확인 → 엔진 조립 → 화면 실행.  사용: python -m sukpago"""

from __future__ import annotations

import sys


def _print_progress(name: str, done: int, total: int) -> None:
    pct = done * 100 // total if total else 0
    print(f"\r  모델 받는 중  {name}  {done / 2**20:.0f}/{total / 2**20:.0f}MB ({pct}%)", end="", flush=True)
    if total and done >= total:
        print()


def _ensure_models() -> str | None:
    """빠진 모델을 받는다. 실패하면 안내 문구를 돌려주고, 앱은 할 수 있는 만큼 계속 실행한다."""
    from . import models

    try:
        models.ensure("app", progress=_print_progress)
    except Exception as e:  # 네트워크가 없거나 파일이 깨졌을 때
        return f"모델 준비 실패: {e}"
    return None


def main() -> int:
    from . import config, engines, paths
    from .asr.mic import Mic
    from .asr.zipformer import ZipformerRecognizer
    from .audio import Player
    from .pipeline import Pipeline, Status
    from .tts.cache import CachedSpeaker
    from .tts.edge import EdgeSpeaker

    problem = _ensure_models()
    settings = config.load_settings()
    glossary = config.load_glossary()
    models_dir = paths.models_dir()

    router = engines.make_router(settings.mymemory_email, models_dir)
    speaker = CachedSpeaker(EdgeSpeaker())
    pipeline = Pipeline(
        recognizer_factory=lambda: ZipformerRecognizer(models_dir / "zipformer-ko"),
        router=router,
        speaker=speaker,
        player=Player(),
        mic_factory=lambda device, on_samples: Mic(device, on_samples),
        settings=settings,
        glossary=glossary,
    )
    if problem:
        pipeline.events.put(Status("info", problem))

    from .ui.app import App

    app = App(pipeline, settings, glossary)
    try:
        app.mainloop()
    finally:
        pipeline.shutdown()
        config.save_settings(settings)
    return 0


if __name__ == "__main__":
    sys.exit(main())
