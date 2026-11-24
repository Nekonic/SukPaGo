import wave

import numpy as np
import pytest

from sukpago.asr.base import Framer, load_wav_16k_mono


def test_framer_keeps_remainder():
    f = Framer(4)
    out = f.push(np.arange(6, dtype=np.float32))
    assert [x.tolist() for x in out] == [[0, 1, 2, 3]]
    out = f.push(np.arange(6, 9, dtype=np.float32))
    assert [x.tolist() for x in out] == [[4, 5, 6, 7]]
    assert f.rest().tolist() == [8]
    assert f.rest().tolist() == []
    assert out[0].dtype == np.float32


def write_wav(path, rate=16000, channels=1, frames=None):
    frames = frames if frames is not None else np.array([0, 16384, -16384], dtype=np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(np.repeat(frames, channels).tobytes())


def test_load_wav(tmp_path):
    p = tmp_path / "a.wav"
    write_wav(p)
    x = load_wav_16k_mono(p)
    assert x.dtype == np.float32
    assert x.tolist() == [0.0, 0.5, -0.5]


@pytest.mark.parametrize("rate,channels", [(44100, 1), (16000, 2)])
def test_load_wav_rejects_wrong_format(tmp_path, rate, channels):
    p = tmp_path / "b.wav"
    write_wav(p, rate=rate, channels=channels)
    with pytest.raises(ValueError, match="16kHz"):
        load_wav_16k_mono(p)
