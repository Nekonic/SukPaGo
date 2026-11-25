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
    read_aloud: bool = False
    pinned: bool = True
    mymemory_email: str = "abcd@gmail.com"
    mic_device: str | None = None
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
    assert isinstance(ev, MicLevel)
    assert ev.state == "silent"


def test_filler_only_final_makes_no_final(pipes):
    p, *_, mics = pipes([[("final", "어 음")], [("final", "다음 문장으로 넘어갈게요")]])
    p.start_live()
    feed(mics[0])
    feed(mics[0])
    ev = next_event(p)
    assert isinstance(ev, Final)
    assert ev.ko == "다음 문장으로 넘어갈게요"


def test_submit_text_translates_then_plays(pipes):
    p, _, speaker, player, _ = pipes()
    seq = p.submit_text("질문 있나요?")
    assert next_event(p) == Final(seq, "질문 있나요?", "text")
    assert [next_event(p).lang for _ in range(2)] == ["mn", "zh"]
    kind, clips = player.played.get(timeout=TIMEOUT)
    assert kind == "clips"
    assert clips == ["mn|mn:질문 있나요?".encode(), "zh|zh:질문 있나요?".encode()]


@pytest.mark.parametrize("read_aloud", [False, True])
def test_live_read_aloud_setting(pipes, read_aloud):
    settings = FakeSettings(langs=["mn"], read_aloud=read_aloud)
    p, _, speaker, player, mics = pipes([[("final", "실시간 강의 문장입니다")]], settings=settings)
    p.start_live()
    feed(mics[0])
    assert isinstance(next_event(p), Final)
    assert isinstance(next_event(p), Translation)
    # 표시로 쓰는 직접 입력: 음성 스레드는 순서대로 처리하므로 이 재생보다 앞선 재생이 있으면 먼저 나온다.
    p.submit_text("표시용 문장")
    first = player.played.get(timeout=TIMEOUT)
    if read_aloud:
        assert first == ("clips", ["mn|mn:실시간 강의 문장입니다".encode()])
        first = player.played.get(timeout=TIMEOUT)
    assert first == ("clips", ["mn|mn:표시용 문장".encode()])


def test_quota_status_only_once(pipes):
    router = FakeRouter(reason="quota", fell_back=True)
    p, *_ = pipes(router=router, settings=FakeSettings(langs=["mn", "zh"]))
    p.submit_text("첫 문장")
    p.submit_text("둘째 문장")
    seen = []
    while sum(isinstance(e, Translation) for e in seen) < 4:
        seen.append(next_event(p))
    statuses = [e for e in seen if isinstance(e, Status)]
    assert [s.kind for s in statuses] == ["quota"]


def test_fallback_status(pipes):
    p, *_ = pipes(router=FakeRouter(reason="error", fell_back=True), settings=FakeSettings(langs=["mn"]))
    p.submit_text("문장")
    kinds = [type(next_event(p)).__name__ for _ in range(3)]
    assert kinds == ["Final", "Translation", "Status"]


def test_mic_open_failure(pipes):
    p, *_ = pipes(mic_fail=True)
    p.start_live()
    ev = next_event(p)
    assert isinstance(ev, Status) and ev.kind == "mic_error"
    assert not p.live


def test_offline_speak_does_not_call_speaker(pipes):
    settings = FakeSettings(online=False, langs=["mn"])
    p, _, speaker, player, _ = pipes(settings=settings)
    p.speak({"mn": "오프라인"})
    p.set_online(True)
    p.speak({"mn": "온라인"})
    assert player.played.get(timeout=TIMEOUT) == ("clips", [b"mn|\xec\x98\xa8\xeb\x9d\xbc\xec\x9d\xb8"])
    assert speaker.calls == [("온라인", "mn")]


def test_speak_uses_target_order_and_enabled_langs(pipes):
    p, _, speaker, player, _ = pipes(settings=FakeSettings(langs=["zh", "mn"]))
    p.speak({"en": "E", "zh": "Z", "mn": "M"})
    assert player.played.get(timeout=TIMEOUT) == ("clips", [b"mn|M", b"zh|Z"])


def test_tts_error_becomes_status(pipes):
    p, _, speaker, player, _ = pipes(settings=FakeSettings(langs=["mn"]))

    class TtsError(Exception):
        pass

    def boom(text, lang):
        raise TtsError("네트워크")

    speaker.synth = boom
    p.speak({"mn": "M"})
    ev = next_event(p)
    assert isinstance(ev, Status) and ev.kind == "tts_error"


def test_audio_error_becomes_status(pipes):
    p, _, speaker, player, _ = pipes(settings=FakeSettings(langs=["mn"]))

    class AudioError(Exception):
        pass

    def boom(clips):
        raise AudioError("장치 없음")

    player.play = boom
    p.speak({"mn": "M"})
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


def test_translate_once(pipes):
    p, *_ = pipes(settings=FakeSettings(langs=["zh", "mn"]))
    assert p.translate_once("안녕") == {"mn": "mn:안녕", "zh": "zh:안녕"}


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
