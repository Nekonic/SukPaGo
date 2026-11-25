"""화면 연기 테스트: 가짜 pipeline·설정으로 창을 만들고 이벤트를 그려 본다. 화면이 없으면 건너뛴다."""

from __future__ import annotations

import queue
import tkinter
from dataclasses import dataclass, field

import pytest

ctk = pytest.importorskip("customtkinter")

from sukpago.text.glossary import Glossary  # noqa: E402


@dataclass(frozen=True)
class Partial:
    text: str


@dataclass(frozen=True)
class Final:
    seq: int
    ko: str
    source: str = "live"


@dataclass(frozen=True)
class Translation:
    seq: int
    lang: str
    text: str
    engine: str = "MyMemory"
    fell_back: bool = False
    reason: str | None = None


@dataclass(frozen=True)
class MicLevel:
    dbfs: float
    state: str


@dataclass(frozen=True)
class Status:
    kind: str
    message: str


@dataclass
class FakeSettings:
    online: bool = True
    langs: list[str] = field(default_factory=lambda: ["mn", "zh"])
    mymemory_email: str = "abcd@gmail.com"
    main_geometry: str | None = None
    display_geometry: str | None = None
    display_font_px: int = 52


@dataclass(frozen=True)
class FakePhrase:
    key: str
    ko: str
    texts: dict


class FakePipeline:
    def __init__(self):
        self.events = queue.Queue()
        self.calls = []
        self.live = False

    def set_langs(self, langs):
        self.calls.append(("langs", list(langs)))

    def set_online(self, online):
        self.calls.append(("online", online))

    def set_glossary(self, g):
        self.calls.append(("glossary", g))

    def start_live(self):
        self.live = True

    def stop_live(self):
        self.live = False

    def play_phrase(self, phrase):
        self.calls.append(("phrase", phrase.key))


class FakePhrases:
    @staticmethod
    def load_all():
        return [FakePhrase(f"p{i}", f"문장{i}", {"mn": f"M{i}", "zh": f"Z{i}", "en": f"E{i}"})
                for i in range(1, 6)]


class FakeConfig:
    def __init__(self):
        self.saved = 0
        self.glossary_saved = None

    def save_settings(self, s):
        self.saved += 1

    def save_glossary(self, g):
        self.glossary_saved = g


@pytest.fixture
def app():
    from sukpago.ui.app import App

    pipeline, config = FakePipeline(), FakeConfig()
    try:
        a = App(pipeline, FakeSettings(), Glossary(), phrases_api=FakePhrases, config_api=config)
    except tkinter.TclError as e:
        pytest.skip(f"화면 없음: {e}")
    a.withdraw()
    yield a, pipeline, config
    a.destroy()


def drain(a):
    a._poll()
    a.update_idletasks()


def test_events_update_current_sentence(app):
    a, pipeline, _ = app
    for ev in (Partial("오늘은"), Final(1, "오늘은 광합성을 배울 거예요"),
               Translation(1, "mn", "Өнөөдөр"), Translation(1, "zh", "今天"), Translation(1, "en", "Today")):
        pipeline.events.put(ev)
    drain(a)
    assert a.ko.cget("text") == "오늘은 광합성을 배울 거예요"
    assert a.lines["mn"].cget("text") == "Өнөөдөр"
    assert a.lines["zh"].cget("text") == "今天"
    assert a.lines["en"].cget("text") == ""  # 영어는 꺼져 있다
    assert a.partial.cget("text") == ""


def test_phrase_button_shows_and_plays(app):
    a, pipeline, _ = app
    a.phrase_buttons[1].invoke()
    assert a.ko.cget("text") == "문장2"
    assert a.lines["mn"].cget("text") == "M2"
    assert ("phrase", "p2") in pipeline.calls


def test_last_language_cannot_be_turned_off(app):
    a, pipeline, _ = app
    a.lang_vars["zh"].set(False)
    a._toggle_lang("zh")
    a.lang_vars["mn"].set(False)
    a._toggle_lang("mn")
    assert a.lang_vars["mn"].get() is True
    assert a.settings.langs == ["mn"]


def test_display_window_shows_only_translations(app):
    a, pipeline, _ = app
    a.open_display()
    pipeline.events.put(Final(1, "한국어 원문"))
    pipeline.events.put(Translation(1, "mn", "Монгол"))
    pipeline.events.put(Translation(1, "zh", "中文"))
    drain(a)
    shown = a.display.text.get("1.0", "end").strip().splitlines()
    assert shown == ["Монгол", "中文"]


def test_status_quota_stays_other_clears(app):
    a, pipeline, _ = app
    pipeline.events.put(Status("fallback", "오프라인으로 전환됨 (error)"))
    pipeline.events.put(Final(1, "다음 문장"))
    drain(a)
    assert a.status.cget("text") == ""
    pipeline.events.put(Status("quota", "오늘 번역 한도 초과"))
    pipeline.events.put(Final(2, "그다음 문장"))
    drain(a)
    assert a.status.cget("text") == "오늘 번역 한도 초과"


def test_terms_add_and_remove_inline(app):
    a, pipeline, config = app
    a.term_wrong.insert(0, "노트북 에램")
    a.term_right.insert(0, "NotebookLM")
    a.add_term()
    assert [r.wrong for r in a.glossary.rules] == ["노트북 에램"]
    assert config.glossary_saved is a.glossary
    assert ("glossary", a.glossary) in pipeline.calls
    assert len(a.term_buttons) == 1 and a.term_wrong.get() == ""
    a.term_buttons[0].invoke()
    assert a.glossary.rules == [] and a.term_buttons == []


def test_mic_level_bar(app):
    a, pipeline, _ = app
    pipeline.events.put(MicLevel(-30.0, "ok"))
    drain(a)
    assert abs(a.mic_bar.get() - 0.5) < 0.01
