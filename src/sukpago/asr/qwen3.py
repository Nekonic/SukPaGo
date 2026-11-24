"""문장 단위 한국어 음성 인식: silero VAD + Qwen3-ASR 0.6B (sherpa-onnx int8)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .base import SAMPLE_RATE
from .vad import VadSegmentedRecognizer


class Qwen3AsrRecognizer(VadSegmentedRecognizer):
    name = "Qwen3-ASR"

    def __init__(self, model_dir: Path, vad_model: Path, *, hotwords: tuple[str, ...] = (),
                 num_threads: int = 2, min_silence: float = 0.5, max_speech: float = 15.0) -> None:
        import sherpa_onnx

        d = Path(model_dir)
        self._rec = sherpa_onnx.OfflineRecognizer.from_qwen3_asr(
            conv_frontend=str(d / "conv_frontend.onnx"),
            encoder=str(d / "encoder.int8.onnx"),
            decoder=str(d / "decoder.int8.onnx"),
            tokenizer=str(d / "tokenizer"),
            hotwords=",".join(hotwords),
            num_threads=num_threads,
            max_new_tokens=256,
        )
        super().__init__(vad_model, min_silence=min_silence, max_speech=max_speech)

    def _decode(self, samples: np.ndarray) -> str:
        stream = self._rec.create_stream()
        stream.set_option("language", "Korean")
        stream.accept_waveform(SAMPLE_RATE, samples)
        self._rec.decode_stream(stream)
        return stream.result.text
