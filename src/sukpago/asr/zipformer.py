"""스트리밍 한국어 음성 인식: kangkyu Zipformer (sherpa-onnx int8)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .base import SAMPLE_RATE, AsrEvent


MAX_UTTERANCE_S = 20.0  # sherpa rule3: 쉬지 않아도 이 길이가 되면 끊는다


class ZipformerRecognizer:
    name = "Zipformer"

    def __init__(self, model_dir: Path, *, chunk: int = 64, num_threads: int = 2) -> None:
        import sherpa_onnx

        model_dir = Path(model_dir)

        def part(kind: str) -> str:
            return str(model_dir / f"{kind}-epoch-99-avg-1-chunk-{chunk}-left-128.int8.onnx")

        self._rec = sherpa_onnx.OnlineRecognizer.from_transducer(
            tokens=str(model_dir / "tokens.txt"),
            encoder=part("encoder"), decoder=part("decoder"), joiner=part("joiner"),
            num_threads=num_threads, sample_rate=SAMPLE_RATE, feature_dim=80,
            enable_endpoint_detection=True,
            rule1_min_trailing_silence=1.2, rule2_min_trailing_silence=0.6,
            rule3_min_utterance_length=MAX_UTTERANCE_S,  # 쉬지 않고 이어지는 말도 단어 중간에서 덜 끊기게
            decoding_method="greedy_search",
        )
        self._pad_s = chunk * 0.04  # 모델 카드 권장: 끝에 CHUNK × 0.04초 무음
        self._stream = self._rec.create_stream()
        self._last = ""
        self._fed = 0
        self._utt_from = 0  # 지금 발화가 시작된 샘플 위치(마지막 리셋)

    def accept(self, samples: np.ndarray) -> list[AsrEvent]:
        samples = np.asarray(samples, dtype=np.float32)
        self._fed += len(samples)
        self._stream.accept_waveform(SAMPLE_RATE, samples)
        while self._rec.is_ready(self._stream):
            self._rec.decode_stream(self._stream)
        text = self._text()
        t = self._fed / SAMPLE_RATE
        events: list[AsrEvent] = []
        if text != self._last:
            events.append(AsrEvent("partial", text, t))
            self._last = text
        if self._rec.is_endpoint(self._stream):
            if text:
                events.append(AsrEvent("final", text, t, self._forced()))
            self._rec.reset(self._stream)
            self._utt_from = self._fed
            self._last = ""
        return events

    def finish(self) -> list[AsrEvent]:
        pad = np.zeros(int(self._pad_s * SAMPLE_RATE), dtype=np.float32)
        self._stream.accept_waveform(SAMPLE_RATE, pad)
        self._stream.input_finished()
        while self._rec.is_ready(self._stream):
            self._rec.decode_stream(self._stream)
        text = self._text()
        self._stream = self._rec.create_stream()
        self._last = ""
        self._utt_from = self._fed
        return [AsrEvent("final", text, self._fed / SAMPLE_RATE)] if text else []

    def _forced(self) -> bool:
        """최대 길이에 걸려 말하는 도중 끊겼는가. 자연스럽게 쉰 끝점은 마지막 낱말 뒤에 1초 안팎의 무음이 있다."""
        dur = (self._fed - self._utt_from) / SAMPLE_RATE
        if dur < MAX_UTTERANCE_S - 0.5:
            return False
        ts = self._rec.get_result_all(self._stream).timestamps
        return bool(ts) and dur - ts[-1] < 0.5

    def _text(self) -> str:
        # sherpa-onnx 1.13.x의 get_result()는 한글 사이 공백을 지운다(issue #4128).
        # 토큰에는 공백("▁" 또는 " ")이 남아 있으므로 토큰을 이어 붙여 복원한다.
        tokens = self._rec.get_result_all(self._stream).tokens
        return " ".join("".join(tokens).replace("▁", " ").split())
