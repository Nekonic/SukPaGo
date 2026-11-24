"""문장 단위 한국어 음성 인식: silero VAD + SenseVoice 2024-07-17 (sherpa-onnx int8)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .base import SAMPLE_RATE, AsrEvent, Framer


class SenseVoiceRecognizer:
    name = "SenseVoice"

    def __init__(self, model_dir: Path, vad_model: Path, *, num_threads: int = 2,
                 min_silence: float = 0.5, max_speech: float = 15.0) -> None:
        import sherpa_onnx

        model_dir = Path(model_dir)
        self._rec = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=str(model_dir / "model.int8.onnx"), tokens=str(model_dir / "tokens.txt"),
            language="ko", use_itn=True, num_threads=num_threads,
        )
        cfg = sherpa_onnx.VadModelConfig()
        cfg.silero_vad.model = str(vad_model)
        cfg.silero_vad.min_silence_duration = min_silence
        cfg.silero_vad.max_speech_duration = max_speech
        cfg.sample_rate = SAMPLE_RATE
        self._vad = sherpa_onnx.VoiceActivityDetector(cfg, buffer_size_in_seconds=60)
        self._framer = Framer(512)

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
            stream = self._rec.create_stream()
            stream.accept_waveform(SAMPLE_RATE, seg.samples)
            self._rec.decode_stream(stream)
            text = stream.result.text.strip()
            if text:
                events.append(AsrEvent("final", text, (seg.start + len(seg.samples)) / SAMPLE_RATE))
            self._vad.pop()
        return events
