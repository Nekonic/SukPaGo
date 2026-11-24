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
