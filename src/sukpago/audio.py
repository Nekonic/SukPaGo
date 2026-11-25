"""mp3·wav 재생기(miniaudio). play()는 바로 돌아오고 소리는 장치 스레드에서 나온다."""

from __future__ import annotations

import threading
from collections.abc import Callable, Generator
from pathlib import Path

SAMPLE_RATE = 24000   # edge-tts mp3가 24kHz 모노라 그대로 맞춘다
NCHANNELS = 1
SAMPLE_WIDTH = 2      # 16비트


class AudioError(Exception):
    """디코딩 실패, 파일 없음, 재생 장치 없음."""


def decode(data: bytes, *, sample_rate: int = SAMPLE_RATE, nchannels: int = NCHANNELS) -> bytes:
    """mp3/wav/flac 바이트를 16비트 PCM 바이트로 바꾼다."""
    import miniaudio

    try:
        sound = miniaudio.decode(data, output_format=miniaudio.SampleFormat.SIGNED16,
                                 nchannels=nchannels, sample_rate=sample_rate)
    except Exception as e:
        raise AudioError(f"오디오를 읽을 수 없음: {e}") from e
    return sound.samples.tobytes()


def _default_device(sample_rate: int, nchannels: int):
    import miniaudio

    return miniaudio.PlaybackDevice(output_format=miniaudio.SampleFormat.SIGNED16,
                                    nchannels=nchannels, sample_rate=sample_rate,
                                    app_name="SukPaGo")


class _Session:
    def __init__(self) -> None:
        self.stopped = threading.Event()
        self.done = threading.Event()


class Player:
    def __init__(self, *, device_factory: Callable[[int, int], object] | None = None,
                 sample_rate: int = SAMPLE_RATE, nchannels: int = NCHANNELS):
        self.sample_rate = sample_rate
        self.nchannels = nchannels
        self._factory = device_factory or _default_device
        self._lock = threading.Lock()
        self._device = None
        self._session: _Session | None = None

    def play(self, clips: list[bytes]) -> None:
        """클립을 차례로 이어서 재생한다. 재생 중이면 멈추고 새로 시작한다."""
        pcm = b"".join(decode(c, sample_rate=self.sample_rate, nchannels=self.nchannels)
                       for c in clips)
        with self._lock:
            self._stop_locked()
            if not pcm:
                return
            session = _Session()
            gen = self._stream(pcm, session)
            next(gen)   # miniaudio는 시작된 제너레이터를 받는다
            try:
                device = self._factory(self.sample_rate, self.nchannels)
                device.start(gen)
            except Exception as e:
                session.stopped.set()
                raise AudioError(f"재생 장치를 열 수 없음: {e}") from e
            self._device = device
            self._session = session

    def play_files(self, paths: list[Path]) -> None:
        clips = []
        for p in paths:
            try:
                clips.append(Path(p).read_bytes())
            except OSError as e:
                raise AudioError(f"오디오 파일을 읽을 수 없음: {p}") from e
        self.play(clips)

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()

    @property
    def playing(self) -> bool:
        s = self._session
        return s is not None and not s.stopped.is_set() and not s.done.is_set()

    def _stop_locked(self) -> None:
        if self._session is not None:
            self._session.stopped.set()
            self._session = None
        if self._device is not None:
            try:
                self._device.close()
            except Exception:
                pass
            self._device = None

    def _stream(self, pcm: bytes, session: _Session) -> Generator[bytes, int, None]:
        frame_bytes = SAMPLE_WIDTH * self.nchannels
        view = memoryview(pcm)
        pos = 0
        try:
            frames = yield b""
            while pos < len(view) and not session.stopped.is_set():
                n = frames * frame_bytes
                chunk = view[pos:pos + n]
                pos += n
                frames = yield chunk
        finally:
            session.done.set()
