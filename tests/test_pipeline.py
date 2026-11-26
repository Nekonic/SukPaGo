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
            # (종류, 글자) 또는 (종류, 글자, 강제 끊김)
            return [AsrEvent(e[0], e[1], 0.0, *e[2:]) for e in self.script.pop(0)]
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


class SlowRouter(FakeRouter):
    def translate(self, text, lang, *, online):
        time.sleep(0.3)
        return super().translate(text, lang, online=online)


def test_languages_are_translated_in_parallel_but_emitted_in_order(pipes):
    p, *_, mics = pipes([[("final", "세 언어로 동시에 번역할 문장입니다")]], router=SlowRouter(),
                        settings=FakeSettings(langs=["mn", "zh", "en"]))
    p.start_live()
    feed(mics[0])
    assert isinstance(next_event(p), Final)
    t0 = time.monotonic()
    langs = [next_event(p).lang for _ in range(3)]
    assert langs == ["mn", "zh", "en"]
    assert time.monotonic() - t0 < 0.75  # 차례로 하면 0.9초 이상



class BatchRouter(FakeRouter):
    def __init__(self):
        super().__init__(reason="offline")
        self.many = []

    def translate_offline_many(self, text, langs):
        self.many.append((text, list(langs)))
        return {lang: FakeResult(f"{lang}:{text}", "fake", False, "offline") for lang in langs}


def test_offline_translates_all_languages_in_one_call(pipes):
    router = BatchRouter()
    p, *_, mics = pipes([[("final", "오프라인으로 묶어서 번역할 문장입니다")]], router=router,
                        settings=FakeSettings(langs=["mn", "zh", "en"], online=False))
    p.start_live()
    feed(mics[0])
    assert isinstance(next_event(p), Final)
    assert [next_event(p).lang for _ in range(3)] == ["mn", "zh", "en"]
    assert router.many == [("오프라인으로 묶어서 번역할 문장입니다", ["mn", "zh", "en"])]
    assert router.calls == []


def test_clause_is_translated_before_the_final(pipes):
    script = [[("partial", "내용은 크게 달라지지 않았다고 봅니다")],
              [("partial", "내용은 크게 달라지지 않았다고 봅니다 이제")],
              [("partial", "내용은 크게 달라지지 않았다고 봅니다 이제 뒤에")],
              [("final", "내용은 크게 달라지지 않았다고 봅니다 이제 뒤에 실습은 바뀌어요")]]
    p, *_, mics = pipes(script, settings=FakeSettings(langs=["mn"]))
    p.start_live()
    for _ in script:
        feed(mics[0])
    finals = []
    while len(finals) < 2:
        ev = next_event(p)
        if isinstance(ev, Final):
            finals.append(ev.ko)
    assert finals == ["내용은 크게 달라지지 않았다고 봅니다", "이제 뒤에 실습은 바뀌어요"]


class QuotaRouter(BatchRouter):
    quota_exceeded = True

    def translate_offline_many(self, text, langs, **kw):
        self.many.append((text, list(langs), kw))
        return {lang: FakeResult(f"{lang}:{text}", "fake", True, "quota") for lang in langs}


def test_after_quota_online_mode_also_batches_offline(pipes):
    router = QuotaRouter()
    p, *_, mics = pipes([[("final", "한도를 넘긴 뒤에 번역할 문장입니다")]], router=router,
                        settings=FakeSettings(langs=["mn", "zh", "en"], online=True))
    p.start_live()
    feed(mics[0])
    assert isinstance(next_event(p), Final)
    langs = [e.lang for e in (next_event(p) for _ in range(4)) if isinstance(e, Translation)]
    assert langs == ["mn", "zh", "en"]
    assert router.many == [("한도를 넘긴 뒤에 번역할 문장입니다", ["mn", "zh", "en"], {"fell_back": True, "reason": "quota"})]
    assert router.calls == []


class PartlyFailingRouter(BatchRouter):
    def translate_offline_many(self, text, langs, **kw):
        out = super().translate_offline_many(text, langs)
        out["zh"] = RuntimeError("빈 번역")
        return out


def test_offline_one_language_failure_keeps_others(pipes):
    p, *_, mics = pipes([[("final", "한 언어만 실패하는 문장입니다")]], router=PartlyFailingRouter(),
                        settings=FakeSettings(langs=["mn", "zh", "en"], online=False))
    p.start_live()
    feed(mics[0])
    assert isinstance(next_event(p), Final)
    evs = [next_event(p) for _ in range(3)]
    assert [e.lang for e in evs if isinstance(e, Translation)] == ["mn", "en"]
    assert any(isinstance(e, Status) and "zh" in e.message for e in evs)



def test_glossary_applied_before_clause_split(pipes):
    from sukpago.text.glossary import Glossary, Rule
    script = [[("partial", "그래서 이번 시간에 데이터 분석할 때는 판다 스를")],
              [("partial", "그래서 이번 시간에 데이터 분석할 때는 판다 스를 많이")],
              [("final", "그래서 이번 시간에 데이터 분석할 때는 판다 스를 많이 씁니다")]]
    p, *_, mics = pipes(script, settings=FakeSettings(langs=["mn"]),
                        glossary=Glossary([Rule("판다 스", "pandas")]))
    p.start_live()
    for _ in script:
        feed(mics[0])
    ev = next_event(p)
    while not isinstance(ev, Final):
        ev = next_event(p)
    assert ev.ko == "그래서 이번 시간에 데이터 분석할 때는 pandas를 많이 씁니다"


def test_stop_after_early_clause_flushes_the_rest(pipes):
    script = [[("partial", "내용은 크게 달라지지 않았다고 봅니다 이제")],
              [("partial", "내용은 크게 달라지지 않았다고 봅니다 이제 뒤에")]]
    p, *_, mics = pipes(script, settings=FakeSettings(langs=["mn"]))
    rec = p._recognizer_factory()
    rec.finish = lambda: [AsrEvent("final", "내용은 크게 달라지지 않았다고 봅니다 이제 뒤에 실습", 3.0)]
    p.start_live()
    for _ in script:
        feed(mics[0])
    first = next_event(p)
    while not isinstance(first, Final):
        first = next_event(p)
    assert first.ko == "내용은 크게 달라지지 않았다고 봅니다"
    p.stop_live()
    ev = next_event(p)
    while not isinstance(ev, Final):
        ev = next_event(p)
    assert ev.ko == "이제 뒤에 실습"



def test_glossary_change_mid_utterance_does_not_lose_text(pipes):
    g = Glossary()
    script = [[("partial", "오늘은 에이 피 아이를 직접 호출해 봅니다 그리고 결과를")],
              [("partial", "오늘은 에이 피 아이를 직접 호출해 봅니다 그리고 결과를 받아서")],
              [("final", "오늘은 에이 피 아이를 직접 호출해 봅니다 그리고 결과를 받아서 화면에 보여줍니다")]]
    p, *_, mics = pipes(script, settings=FakeSettings(langs=["mn"]), glossary=g)
    p.start_live()
    feed(mics[0]); feed(mics[0])
    finals = []
    while not finals:
        ev = next_event(p)
        if isinstance(ev, Final):
            finals.append(ev.ko)
    g.add("에이피아이", "API")
    p.set_glossary(g)
    feed(mics[0])
    while len(finals) < 2:
        ev = next_event(p)
        if isinstance(ev, Final):
            finals.append(ev.ko)
    assert finals[1].startswith("그리고 결과를 받아서")


def _finals_of(p, n):
    out = []
    while len(out) < n:
        ev = next_event(p)
        if isinstance(ev, Final):
            out.append(ev.ko)
    return out


@pytest.mark.parametrize("forced", [True, False])
def test_glossary_term_split_across_pieces_is_fixed_once(pipes, forced):
    script = [[("final", "오늘은 우리가 수업에서 자바", forced)],
              [("final", "스크립트로 화면을 만들어 볼 거예요")]]
    p, *_, mics = pipes(script, settings=FakeSettings(langs=["mn"]),
                        glossary=Glossary([Rule("자바", "자바스크립트")]))
    p.start_live()
    feed(mics[0]); feed(mics[0])
    assert _finals_of(p, 1) == ["오늘은 우리가 수업에서 자바 스크립트로 화면을 만들어 볼 거예요"]


def test_copula_after_forced_cut_is_glued(pipes):
    p, *_, mics = pipes([[("final", "중요한 것은 독자의 관점", True)], [("final", "입니다 그래서 이렇게 씁니다")]],
                        settings=FakeSettings(langs=["mn"]))
    p.start_live()
    feed(mics[0]); feed(mics[0])
    assert _finals_of(p, 1) == ["중요한 것은 독자의 관점입니다 그래서 이렇게 씁니다"]
