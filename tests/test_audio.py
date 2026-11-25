import array
import io
import wave

import pytest

from sukpago.audio import AudioError, Player, decode


def make_wav(values, rate=24000):
    """16비트 모노 wav 바이트."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(array.array("h", values).tobytes())
    return buf.getvalue()


class FakeDevice:
    def __init__(self):
        self.gen = None
        self.closed = False

    def start(self, gen):
        self.gen = gen

    def close(self):
        self.closed = True


class FakeFactory:
    def __init__(self):
        self.devices = []
        self.args = []

    def __call__(self, sample_rate, nchannels):
        self.args.append((sample_rate, nchannels))
        d = FakeDevice()
        self.devices.append(d)
        return d


def drain(gen, frames=7):
    """장치처럼 프레임 수를 보내며 나오는 샘플을 모은다."""
    out = array.array("h")
    try:
        while True:
            chunk = gen.send(frames)
            assert len(chunk) <= frames * 2
            out.frombytes(bytes(chunk))
    except StopIteration:
        pass
    return list(out)


def test_decode_wav_to_16bit_pcm():
    pcm = decode(make_wav([0, 1000, -1000, 32767]), sample_rate=24000, nchannels=1)
    assert list(array.array("h", pcm)) == [0, 1000, -1000, 32767]


def test_decode_garbage_is_audio_error():
    with pytest.raises(AudioError):
        decode(b"not audio at all", sample_rate=24000, nchannels=1)


def test_plays_two_clips_in_order():
    f = FakeFactory()
    p = Player(device_factory=f)
    a = list(range(1, 11))
    b = list(range(-1, -16, -1))
    p.play([make_wav(a), make_wav(b)])
    assert p.playing
    assert f.args == [(p.sample_rate, p.nchannels)]
    assert drain(f.devices[0].gen) == a + b
    assert not p.playing


def test_stop_ends_playback_and_closes_device():
    f = FakeFactory()
    p = Player(device_factory=f)
    p.play([make_wav([5] * 100)])
    gen = f.devices[0].gen
    gen.send(10)
    p.stop()
    assert not p.playing
    assert f.devices[0].closed
    with pytest.raises(StopIteration):
        gen.send(10)


def test_play_replaces_previous_playback():
    f = FakeFactory()
    p = Player(device_factory=f)
    p.play([make_wav([1] * 100)])
    p.play([make_wav([2, 3])])
    assert f.devices[0].closed
    assert drain(f.devices[1].gen) == [2, 3]


def test_play_files(tmp_path):
    f = FakeFactory()
    p = Player(device_factory=f)
    one, two = tmp_path / "1.wav", tmp_path / "2.wav"
    one.write_bytes(make_wav([1, 2]))
    two.write_bytes(make_wav([3]))
    p.play_files([one, two])
    assert drain(f.devices[0].gen) == [1, 2, 3]


def test_play_files_missing_is_audio_error(tmp_path):
    p = Player(device_factory=FakeFactory())
    with pytest.raises(AudioError):
        p.play_files([tmp_path / "none.mp3"])


def test_no_device_is_audio_error():
    def no_device(sample_rate, nchannels):
        raise RuntimeError("no playback device")

    p = Player(device_factory=no_device)
    with pytest.raises(AudioError):
        p.play([make_wav([1, 2, 3])])
    assert not p.playing


def test_device_start_failure_is_audio_error():
    class Broken(FakeDevice):
        def start(self, gen):
            raise OSError("device busy")

    p = Player(device_factory=lambda sr, ch: Broken())
    with pytest.raises(AudioError):
        p.play([make_wav([1])])
    assert not p.playing


def test_empty_clip_list_just_stops():
    f = FakeFactory()
    p = Player(device_factory=f)
    p.play([make_wav([1] * 50)])
    p.play([])
    assert f.devices[0].closed
    assert len(f.devices) == 1
    assert not p.playing
