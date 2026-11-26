import queue
import threading
import time
from dataclasses import dataclass, field

import numpy as np
import pytest

from sukpago.asr.base import AsrEvent
from sukpago.pipeline import Final, MicLevel, Partial, Pipeline, Status, Translation
from sukpago.text.glossary import Glossary, Rule

TIMEOUT = 2


@dataclass
class FakeSettings:
    online: bool = True
    langs: list[str] = field(default_factory=lambda: ["mn", "zh"])
    pinned: bool = True
    mymemory_email: str = "abcd@gmail.com"
    main_geometry: str | None = None
    display_geometry: str | None = None
    display_font_px: int = 52
    display_prev_scale: float = 0.75
    display_pinned: bool = True


@dataclass(frozen=True)
class FakeResult:
    text: str
    engine: str
    fell_back: bool
    reason: str | None = None


@dataclass(frozen=True)
class FakePhrase:
    key: str
    ko: str
    texts: dict
    custom: bool = False


class FakeRecognizer:
    name = "fake"

    def __init__(self, script):
        self.script = list(script)  # accept 호출마다 돌려줄 이벤트 목록
        self.finished = False

    def accept(self, samples):
        if self.script:
            return [AsrEvent(kind, text, 0.0) for kind, text in self.script.pop(0)]
        return []

    def finish(self):
        self.finished = True
        return []


class FakeRouter:
    def __init__(self, reason=None, fell_back=False):
        self.reason, self.fell_back, self.calls = reason, fell_back, []

    def translate(self, text, lang, *, online):
        self.calls.append((text, lang, online))
        return FakeResult(f"{lang}:{text}", "fake", self.fell_back, self.reason)


class FakeSpeaker:
    name = "fake-tts"

    def __init__(self):
        self.calls = []

    def synth(self, text, lang):
        self.calls.append((text, lang))
        return f"{lang}|{text}".encode()


class FakePlayer:
    def __init__(self):
        self.played: queue.Queue = queue.Queue()

    def play(self, clips):
        self.played.put(("clips", list(clips)))

    def play_files(self, paths):
        self.played.put(("files", list(paths)))

    def stop(self):
        pass

    @property
    def playing(self):
        return False


class FakeMic:
    def __init__(self, device, on_samples, fail=False):
        self.device, self.on_samples, self.fail = device, on_samples, fail
        self.started = self.stopped = False

    def start(self):
        if self.fail:
            raise RuntimeError("장치 없음")
        self.started = True

    def stop(self):
        self.stopped = True


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def make(script=(), *, router=None, settings=None, glossary=None, mic_fail=False, audio_path=None):
    mics = []

    def mic_factory(device, on_samples):
        m = FakeMic(device, on_samples, fail=mic_fail)
        mics.append(m)
        return m

    rec = FakeRecognizer(script)
    speaker, player = FakeSpeaker(), FakePlayer()
    p = Pipeline(recognizer_factory=lambda: rec, router=router or FakeRouter(),
                 speaker=speaker, player=player, mic_factory=mic_factory,
                 settings=settings or FakeSettings(), glossary=glossary or Glossary(),
                 clock=Clock(), audio_path=audio_path)
    return p, rec, speaker, player, mics


@pytest.fixture
def pipes():
    made = []

    def _make(*args, **kwargs):
        out = make(*args, **kwargs)
        made.append(out[0])
        return out

    yield _make
    for p in made:
        p.shutdown()


def next_event(p, skip=(MicLevel,)):
    while True:
        ev = p.events.get(timeout=TIMEOUT)
        if not isinstance(ev, skip):
            return ev


def feed(mic):
    mic.on_samples(np.zeros(1600, dtype=np.float32))


def test_live_partial_final_translations_in_order(pipes):
    p, *_ , mics = pipes([[("partial", "오늘은 광합성")], [("final", "오늘은 광합성을 배울 거예요")]])
    p.start_live()
    assert p.live
    feed(mics[0])
    feed(mics[0])
    assert next_event(p) == Partial("오늘은 광합성")
    final = next_event(p)
    assert final == Final(final.seq, "오늘은 광합성을 배울 거예요", "live")
    t1, t2 = next_event(p), next_event(p)
    assert isinstance(t1, Translation) and isinstance(t2, Translation)
    assert (t1.seq, t1.lang, t1.text) == (final.seq, "mn", "mn:오늘은 광합성을 배울 거예요")
    assert (t2.seq, t2.lang) == (final.seq, "zh")


def test_mic_level_emitted(pipes):
    p, *_, mics = pipes()
    p.start_live()
    feed(mics[0])
    ev = p.events.get(timeout=TIMEOUT)
    assert isinstance(ev, MicLevel) and ev.state == "silent"


def test_filler_only_final_makes_no_final(pipes):
    p, *_, mics = pipes([[("final", "어 음")], [("final", "다음 문장으로 넘어갈게요")]])
    p.start_live()
    feed(mics[0])
    feed(mics[0])
    ev = next_event(p)
    assert isinstance(ev, Final)
    assert ev.ko == "다음 문장으로 넘어갈게요"


def test_live_sentence_is_not_read_aloud(pipes):
    p, _, speaker, player, mics = pipes([[("final", "실시간 강의 문장입니다")]],
                                        settings=FakeSettings(langs=["mn"]))
    p.start_live()
    feed(mics[0])
    assert isinstance(next_event(p), Final)
    assert isinstance(next_event(p), Translation)
    with pytest.raises(queue.Empty):
        player.played.get(timeout=0.3)
    assert speaker.calls == []


def live_sentences(pipes, router, langs, sentences):
    script = [[("final", s)] for s in sentences]
    p, *_, mics = pipes(script, router=router, settings=FakeSettings(langs=langs))
    p.start_live()
    for _ in sentences:
        feed(mics[0])
    return p


def test_quota_status_only_once(pipes):
    p = live_sentences(pipes, FakeRouter(reason="quota", fell_back=True), ["mn", "zh"],
                       ["첫 번째 문장입니다", "두 번째 문장입니다"])
    seen = []
    while sum(isinstance(e, Translation) for e in seen) < 4:
        seen.append(next_event(p))
    assert [s.kind for s in seen if isinstance(s, Status)] == ["quota"]


def test_fallback_status(pipes):
    p = live_sentences(pipes, FakeRouter(reason="error", fell_back=True), ["mn"], ["대체 번역 문장입니다"])
    kinds = [type(next_event(p)).__name__ for _ in range(3)]
    assert kinds == ["Final", "Translation", "Status"]


def test_mic_open_failure(pipes):
    p, *_ = pipes(mic_fail=True)
    p.start_live()
    ev = next_event(p)
    assert isinstance(ev, Status) and ev.kind == "mic_error"
    assert not p.live


def test_phrase_offline_does_not_synthesize(pipes, tmp_path):
    p, _, speaker, player, _ = pipes(settings=FakeSettings(online=False, langs=["mn"]),
                                     audio_path=lambda ph, lang: tmp_path / f"{ph.key}_{lang}.mp3")
    p.play_phrase(FakePhrase("p1", "집중하세요", {"mn": "M"}))
    with pytest.raises(queue.Empty):
        player.played.get(timeout=0.3)
    assert speaker.calls == []


def test_phrase_synth_uses_target_order(pipes, tmp_path):
    p, _, speaker, player, _ = pipes(settings=FakeSettings(langs=["zh", "mn"]),
                                     audio_path=lambda ph, lang: tmp_path / f"{ph.key}_{lang}.mp3")
    p.play_phrase(FakePhrase("p1", "집중하세요", {"en": "E", "zh": "Z", "mn": "M"}))
    assert player.played.get(timeout=TIMEOUT) == ("clips", [b"mn|M", b"zh|Z"])


def test_tts_error_becomes_status(pipes, tmp_path):
    p, _, speaker, player, _ = pipes(settings=FakeSettings(langs=["mn"]),
                                     audio_path=lambda ph, lang: tmp_path / f"{ph.key}_{lang}.mp3")

    def boom(text, lang):
        raise RuntimeError("네트워크")

    speaker.synth = boom
    p.play_phrase(FakePhrase("p1", "집중하세요", {"mn": "M"}))
    ev = next_event(p)
    assert isinstance(ev, Status) and ev.kind == "tts_error"


def test_audio_error_becomes_status(pipes, tmp_path):
    (tmp_path / "p1_mn.mp3").write_bytes(b"ID3")
    p, _, speaker, player, _ = pipes(settings=FakeSettings(langs=["mn"]),
                                     audio_path=lambda ph, lang: tmp_path / f"{ph.key}_{lang}.mp3")

    def boom(paths):
        raise RuntimeError("장치 없음")

    player.play_files = boom
    p.play_phrase(FakePhrase("p1", "집중하세요", {"mn": "M"}))
    ev = next_event(p)
    assert isinstance(ev, Status) and ev.kind == "audio_error"


def test_play_phrase_uses_files(pipes, tmp_path):
    files = {}
    for lang in ("mn", "zh"):
        files[lang] = tmp_path / f"p1_{lang}.mp3"
        files[lang].write_bytes(b"ID3")
    p, _, speaker, player, _ = pipes(audio_path=lambda ph, lang: tmp_path / f"{ph.key}_{lang}.mp3")
    p.play_phrase(FakePhrase("p1", "집중하세요", {"mn": "M", "zh": "Z", "en": "E"}))
    assert player.played.get(timeout=TIMEOUT) == ("files", [files["mn"], files["zh"]])
    assert speaker.calls == []


def test_play_phrase_synthesizes_missing_file_when_online(pipes, tmp_path):
    (tmp_path / "c1_mn.mp3").write_bytes(b"MNFILE")
    p, _, speaker, player, _ = pipes(audio_path=lambda ph, lang: tmp_path / f"{ph.key}_{lang}.mp3")
    p.play_phrase(FakePhrase("c1", "내 문장", {"mn": "M", "zh": "Z"}, True))
    assert player.played.get(timeout=TIMEOUT) == ("clips", [b"MNFILE", b"zh|Z"])


def test_set_glossary_applies_to_new_sentences(pipes):
    p, *_, mics = pipes([[("final", "오늘은 노트북 에램을 써 봅시다")]])
    p.set_glossary(Glossary([Rule("노트북 에램", "NotebookLM")]))
    p.start_live()
    feed(mics[0])
    ev = next_event(p)
    assert isinstance(ev, Final) and ev.ko == "오늘은 NotebookLM을 써 봅시다"


def test_stop_live_flushes_pending(pipes):
    p, rec, *_, mics = pipes([[("final", "짧은 말")]])
    p.start_live()
    feed(mics[0])
    p.stop_live()
    assert not p.live and rec.finished and mics[0].stopped
    ev = next_event(p)
    assert isinstance(ev, Final) and ev.ko == "짧은 말"


def test_shutdown_stops_threads_within_1s():
    p, *_, mics = make()
    p.start_live()
    threads = [t for t in threading.enumerate() if t.name.startswith("pipeline-")]
    assert threads
    t0 = time.monotonic()
    p.shutdown()
    for t in threads:
        t.join(timeout=max(0.0, 1.0 - (time.monotonic() - t0)))
    assert time.monotonic() - t0 < 1.0
    assert not any(t.is_alive() for t in threads)


class CrashingRecognizer(FakeRecognizer):
    def accept(self, samples):
        raise RuntimeError("모델 오류")


def test_asr_crash_reports_and_stops_mic(pipes):
    p, _, _, _, mics = pipes()
    p._recognizer_factory = lambda: CrashingRecognizer([])
    p.start_live()
    feed(mics[0])
    ev = next_event(p)
    assert isinstance(ev, Status) and ev.kind == "mic_error"
    deadline = time.monotonic() + TIMEOUT
    while p.live and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not p.live and mics[0].stopped
    p.start_live()  # 다시 시작하면 새 마이크 하나만 열린다
    assert len(mics) == 2 and mics[1].started
