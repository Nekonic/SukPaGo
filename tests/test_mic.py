import array

import numpy as np
import pytest

from sukpago.asr import mic
from sukpago.asr.base import SAMPLE_RATE
from sukpago.asr.mic import Mic, MicError, classify, level


def sine(amp: float, n: int = SAMPLE_RATE) -> np.ndarray:
    t = np.arange(n, dtype=np.float32) / SAMPLE_RATE
    return (amp * np.sin(2 * np.pi * 440 * t)).astype(np.float32)


# level / classify


def test_level_sine_half():
    dbfs, clip = level(sine(0.5))
    assert dbfs == pytest.approx(-9.03, abs=0.1)
    assert clip == 0.0
    assert classify(dbfs, clip) == "ok"


def test_level_silent_and_quiet():
    assert classify(*level(sine(0.001))) == "silent"
    assert classify(*level(sine(0.005))) == "quiet"


def test_level_full_scale_is_loud():
    dbfs, clip = level(np.ones(1600, dtype=np.float32))
    assert dbfs == pytest.approx(0.0, abs=1e-6)
    assert clip == 1.0
    assert classify(dbfs, clip) == "loud"


def test_level_empty_and_zeros():
    assert level(np.zeros(0, dtype=np.float32)) == (-120.0, 0.0)
    dbfs, clip = level(np.zeros(100, dtype=np.float32))
    assert dbfs == -120.0 and clip == 0.0


def test_classify_boundaries():
    assert classify(-10.0, 0.01) == "loud"
    assert classify(-10.0, 0.0099) == "ok"
    assert classify(-80.0, 0.5) == "loud"      # loud가 먼저
    assert classify(-60.01, 0.0) == "silent"
    assert classify(-60.0, 0.0) == "quiet"
    assert classify(-40.01, 0.0) == "quiet"
    assert classify(-40.0, 0.0) == "ok"


# 가짜 장치


class FakeDevice:
    def __init__(self, device_id):
        self.device_id = device_id
        self.gen = None
        self.stopped = False
        self.closed = False

    def start(self, gen):
        self.gen = gen

    def stop(self):
        self.stopped = True

    def close(self):
        self.closed = True

    def push(self, n: int, value: float = 0.1):
        """miniaudio처럼 array('f')로 n개 샘플을 보낸다."""
        self.gen.send(array.array("f", [value] * n))


class Factory:
    def __init__(self):
        self.devices: list[FakeDevice] = []

    def __call__(self, device_id):
        d = FakeDevice(device_id)
        self.devices.append(d)
        return d


def make_mic(device=None, captures=None, **kw):
    got: list[np.ndarray] = []
    f = Factory()
    m = Mic(device, got.append, device_factory=f,
            captures=(lambda: captures) if captures is not None else (lambda: []), **kw)
    return m, f, got


def test_mic_chunks_250ms_into_two_100ms():
    m, f, got = make_mic()
    m.start()
    dev = f.devices[0]
    for _ in range(5):              # 50ms씩 5번 = 250ms
        dev.push(800)
    assert len(got) == 2
    assert all(c.dtype == np.float32 and c.shape == (1600,) for c in got)


def test_mic_accepts_bytes_and_uneven_sizes():
    m, f, got = make_mic(chunk_ms=50)
    m.start()
    dev = f.devices[0]
    dev.gen.send(np.full(1000, 0.2, dtype=np.float32).tobytes())
    dev.push(700)
    assert [len(c) for c in got] == [800, 800]
    assert got[0][0] == pytest.approx(0.2)


def test_mic_no_callback_after_stop():
    m, f, got = make_mic()
    m.start()
    dev = f.devices[0]
    dev.push(1200)
    m.stop()
    assert dev.stopped and dev.closed
    try:
        dev.push(4000)
    except StopIteration:
        pass
    assert got == []


def test_mic_stop_twice_and_restart():
    m, f, got = make_mic()
    m.start()
    m.stop()
    m.stop()
    m.start()
    f.devices[-1].push(1600)
    assert len(f.devices) == 2 and len(got) == 1


def test_mic_open_failure_raises_micerror():
    def boom(device_id):
        raise RuntimeError("no device")

    m = Mic(None, lambda s: None, device_factory=boom, captures=lambda: [])
    with pytest.raises(MicError):
        m.start()


def test_mic_start_failure_raises_micerror_and_closes():
    class BadStart(FakeDevice):
        def start(self, gen):
            raise RuntimeError("busy")

    made = []

    def factory(device_id):
        d = BadStart(device_id)
        made.append(d)
        return d

    m = Mic(None, lambda s: None, device_factory=factory, captures=lambda: [])
    with pytest.raises(MicError):
        m.start()
    assert made[0].closed


CAPS = [
    {"name": "Microphone (Realtek(R) Audio)", "id": "id-realtek"},
    {"name": "Headset Microphone (USB Audio)", "id": "id-usb"},
]


def test_mic_device_exact_name():
    m, f, _ = make_mic("Headset Microphone (USB Audio)", CAPS)
    m.start()
    assert f.devices[0].device_id == "id-usb"


def test_mic_device_case_insensitive_contains():
    m, f, _ = make_mic("realtek", CAPS)
    m.start()
    assert f.devices[0].device_id == "id-realtek"


def test_mic_device_none_uses_default():
    m, f, _ = make_mic(None, CAPS)
    m.start()
    assert f.devices[0].device_id is None


def test_mic_device_missing_falls_back_to_default():
    m, f, _ = make_mic("Nonexistent", CAPS)
    m.start()
    assert f.devices[0].device_id is None


def test_mic_callback_error_does_not_kill_capture():
    got = []

    def cb(s):
        got.append(s)
        if len(got) == 1:
            raise ValueError("ui bug")

    f = Factory()
    m = Mic(None, cb, device_factory=f, captures=lambda: [])
    m.start()
    f.devices[0].push(1600)
    f.devices[0].push(1600)
    assert len(got) == 2


# list_devices


def test_list_devices_failure_returns_empty(monkeypatch):
    class Broken:
        def __init__(self, *a, **k):
            raise RuntimeError("no backend")

    monkeypatch.setattr(mic.miniaudio, "Devices", Broken)
    assert mic.list_devices() == []


def test_list_devices_names(monkeypatch):
    class Fake:
        def get_captures(self):
            return CAPS

    monkeypatch.setattr(mic.miniaudio, "Devices", Fake)
    assert mic.list_devices() == [c["name"] for c in CAPS]
