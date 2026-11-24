"""silero VAD로 말 구간을 자른 뒤 구간마다 인식하는 엔진의 공통 부분."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from .base import SAMPLE_RATE, AsrEvent, Framer


class VadSegmentedRecognizer:
    name = "vad"

    def __init__(self, vad_model: Path | None, *, min_silence: float = 0.5,
                 max_speech: float = 15.0, vad: Any = None) -> None:
        if vad is None:
            import sherpa_onnx

            cfg = sherpa_onnx.VadModelConfig()
            cfg.silero_vad.model = str(vad_model)
            cfg.silero_vad.min_silence_duration = min_silence
            cfg.silero_vad.max_speech_duration = max_speech
            cfg.sample_rate = SAMPLE_RATE
            vad = sherpa_onnx.VoiceActivityDetector(cfg, buffer_size_in_seconds=60)
        self._vad = vad
        self._framer = Framer(512)

    def _decode(self, samples: np.ndarray) -> str:
        raise NotImplementedError

    def accept(self, samples: np.ndarray) -> list[AsrEvent]:
        for frame in self._framer.push(samples):
            self._vad.accept_waveform(frame)
        return self._drain()

    def finish(self) -> list[AsrEvent]:
        rest = self._framer.rest()
        if len(rest):
            self._vad.accept_waveform(rest)
        self._vad.flush()
        return self._drain()

    def _drain(self) -> list[AsrEvent]:
        events: list[AsrEvent] = []
        while not self._vad.empty():
            seg = self._vad.front
            text = self._decode(np.asarray(seg.samples, dtype=np.float32)).strip()
            if text:
                events.append(AsrEvent("final", text, (seg.start + len(seg.samples)) / SAMPLE_RATE))
            self._vad.pop()
        return events
