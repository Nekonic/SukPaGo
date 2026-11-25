"""마이크 캡처와 소리 크기 판정."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Generator
from typing import Any

import miniaudio
import numpy as np

from sukpago.asr.base import SAMPLE_RATE, Framer

log = logging.getLogger(__name__)

CLIP_LEVEL = 0.99


class MicError(Exception):
    pass


def level(samples: np.ndarray) -> tuple[float, float]:
    """(dBFS, |x|>=0.99인 샘플 비율). 빈 배열이나 무음은 (-120.0, 0.0)."""
    x = np.asarray(samples, dtype=np.float32)
    if x.size == 0:
        return -120.0, 0.0
    rms = float(np.sqrt(np.mean(np.square(x, dtype=np.float64))))
    dbfs = 20.0 * np.log10(rms) if rms > 0 else -120.0
    dbfs = max(-120.0, float(dbfs))
    clip = float(np.count_nonzero(np.abs(x) >= CLIP_LEVEL)) / x.size
    return dbfs, clip


def classify(dbfs: float, clip_ratio: float) -> str:
    if clip_ratio >= 0.01:
        return "loud"
    if dbfs < -60:
        return "silent"
    if dbfs < -40:
        return "quiet"
    return "ok"


def _default_captures() -> list[dict[str, Any]]:
    return miniaudio.Devices().get_captures()


def _default_device_factory(device_id: Any) -> miniaudio.CaptureDevice:
    return miniaudio.CaptureDevice(
        input_format=miniaudio.SampleFormat.FLOAT32,
        nchannels=1,
        sample_rate=SAMPLE_RATE,
        device_id=device_id,
    )


def _find_device_id(name: str, captures: list[dict[str, Any]]) -> Any | None:
    """같은 이름을 먼저, 없으면 대소문자 무시 포함 관계로 찾는다."""
    for d in captures:
        if d.get("name") == name:
            return d.get("id")
    key = name.strip().casefold()
    if key:
        for d in captures:
            if key in str(d.get("name", "")).casefold():
                return d.get("id")
    return None


class _Run:
    """start 한 번에 해당하는 캡처 상태."""

    def __init__(self) -> None:
        self.active = True


class Mic:
    def __init__(
        self,
        device: str | None,
        on_samples: Callable[[np.ndarray], None],
        *,
        chunk_ms: int = 100,
        device_factory: Callable[[Any], Any] | None = None,
        captures: Callable[[], list[dict[str, Any]]] | None = None,
    ) -> None:
        self.device = device
        self.on_samples = on_samples
        self.chunk = max(1, SAMPLE_RATE * chunk_ms // 1000)
        self._factory = device_factory or _default_device_factory
        self._captures = captures or _default_captures
        self._lock = threading.RLock()
        self._dev: Any = None
        self._run: _Run | None = None

    def _resolve_id(self) -> Any | None:
        if not self.device:
            return None
        try:
            caps = self._captures()
        except Exception:
            log.exception("마이크 목록을 읽지 못해 기본 장치를 씁니다")
            return None
        dev_id = _find_device_id(self.device, caps)
        if dev_id is None:
            log.warning("마이크 %r을 찾지 못해 기본 장치를 씁니다", self.device)
        return dev_id

    def _generator(self, run: _Run) -> Generator[None, Any, None]:
        framer = Framer(self.chunk)
        while True:
            data = yield
            with self._lock:
                if not run.active:
                    return
                if isinstance(data, (bytes, bytearray, memoryview)):
                    x = np.frombuffer(data, dtype=np.float32)
                else:
                    x = np.asarray(data, dtype=np.float32)
                for frame in framer.push(x):
                    if not run.active:
                        return
                    try:
                        self.on_samples(frame.copy())
                    except Exception:
                        log.exception("마이크 콜백 오류")

    def start(self) -> None:
        with self._lock:
            if self._run is not None:
                return
            run = _Run()
            try:
                dev = self._factory(self._resolve_id())
            except Exception as e:
                raise MicError(f"마이크를 열지 못했습니다: {e}") from e
            gen = self._generator(run)
            next(gen)
            try:
                dev.start(gen)
            except Exception as e:
                run.active = False
                _close(dev)
                raise MicError(f"마이크를 시작하지 못했습니다: {e}") from e
            self._dev, self._run = dev, run

    def stop(self) -> None:
        with self._lock:
            run, dev = self._run, self._dev
            self._run = self._dev = None
            if run is not None:
                run.active = False
        if dev is not None:
            _close(dev)


def _close(dev: Any) -> None:
    for name in ("stop", "close"):
        try:
            getattr(dev, name)()
        except Exception:
            log.exception("마이크 %s 실패", name)
