import numpy as np

from sukpago.asr.vad import VadSegmentedRecognizer


class Seg:
    def __init__(self, start, samples):
        self.start, self.samples = start, samples


class FakeVad:
    """프레임을 3개 받을 때마다 구간 하나를 낸다."""

    def __init__(self):
        self.frames, self.queue, self.flushed = [], [], False

    def accept_waveform(self, frame):
        self.frames.append(len(frame))
        if len(self.frames) % 3 == 0:
            self.queue.append(Seg(16000 * (len(self.frames) - 3) // 31, np.zeros(1536, np.float32)))

    def flush(self):
        self.flushed = True
        self.queue.append(Seg(0, np.zeros(10, np.float32)))

    def empty(self):
        return not self.queue

    @property
    def front(self):
        return self.queue[0]

    def pop(self):
        self.queue.pop(0)


class Echo(VadSegmentedRecognizer):
    name = "echo"

    def __init__(self, vad):
        super().__init__(None, vad=vad)
        self.n = 0

    def _decode(self, samples):
        self.n += 1
        return f" 문장{self.n} " if len(samples) > 100 else ""


def test_frames_of_512_and_finals_from_segments():
    vad = FakeVad()
    rec = Echo(vad)
    events = rec.accept(np.zeros(1600, np.float32))
    assert vad.frames == [512, 512, 512]
    assert [(e.kind, e.text) for e in events] == [("final", "문장1")]
    events = rec.finish()
    assert vad.flushed and vad.frames[-1] == 1600 - 3 * 512
    assert events == []
