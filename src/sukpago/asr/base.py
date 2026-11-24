"""음성 인식 공통 부분."""

from __future__ import annotations

import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

import numpy as np

SAMPLE_RATE = 16000


@dataclass(frozen=True)
class AsrEvent:
    kind: Literal["partial", "final"]
    text: str
    t: float


class Recognizer(Protocol):
    name: str

    def accept(self, samples: np.ndarray) -> list[AsrEvent]: ...

    def finish(self) -> list[AsrEvent]: ...


class Framer:
    """임의 길이로 들어오는 샘플을 고정 크기 창으로 자른다. 남는 샘플은 다음 호출로 넘긴다."""

    def __init__(self, size: int) -> None:
        self.size = size
        self._buf = np.zeros(0, dtype=np.float32)

    def push(self, samples: np.ndarray) -> list[np.ndarray]:
        self._buf = np.concatenate([self._buf, np.asarray(samples, dtype=np.float32)])
        n = len(self._buf) // self.size * self.size
        frames = [self._buf[i:i + self.size] for i in range(0, n, self.size)]
        self._buf = self._buf[n:]
        return frames

    def rest(self) -> np.ndarray:
        rest, self._buf = self._buf, np.zeros(0, dtype=np.float32)
        return rest


def load_wav_16k_mono(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        if (w.getframerate(), w.getnchannels(), w.getsampwidth()) != (SAMPLE_RATE, 1, 2):
            raise ValueError(f"{path}: 16kHz 모노 16비트 wav만 읽을 수 있습니다")
        data = w.readframes(w.getnframes())
    return np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
