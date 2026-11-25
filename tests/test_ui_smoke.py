"""화면 연기 테스트: 가짜 pipeline·설정·문장으로 창을 만들고 이벤트를 그려 본다. 화면이 없으면 건너뛴다."""

from __future__ import annotations

import queue
import tkinter
from dataclasses import dataclass, field
from pathlib import Path

import pytest

ctk = pytest.importorskip("customtkinter")

from sukpago.text.glossary import Glossary  # noqa: E402


# ---------- 가짜 이벤트(파이프라인 이벤트와 클래스 이름·필드가 같다) ----------

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
class Status:
    kind: str
    message: str


@dataclass(frozen=True)
class MicLevel:
    dbfs: float
    clip_ratio: float
    state: str


@dataclass
class FakeSettings:
    online: bool = True
    langs: list[str] = field(default_factory=lambda: ["mn", "zh"])
    read_aloud: bool = False
    pinned: bool = False
    mymemory_email: str = "abcd@gmail.com"
    mic_device: str | None = None
    main_geometry: str | None = None
    display_geometry: str | None = None
    display_font_px: int = 52
    display_prev_scale: float = 0.75
    display_pinned: bool = False


@dataclass(frozen=True)
class FakePhrase:
    key: str
    ko: str
    texts: dict
    custom: bool


class FakePipeline:
    def __init__(self) -> None:
        self.events: queue.Queue = queue.Queue()
        self.live = False
        self.calls: list[tuple] = []

    def start_live(self):
        self.live = True
        self.calls.append(("start_live",))

    def stop_live(self):
        self.live = False
        self.calls.append(("stop_live",))

    def submit_text(self, ko):
        self.calls.append(("submit_text", ko))
        return 1

    def speak(self, texts):
        self.calls.append(("speak", texts))

    def play_phrase(self, phrase):
        self.calls.append(("play_phrase", phrase.key))

    def translate_once(self, ko):
        return {"mn": "MN:" + ko, "zh": "ZH:" + ko}

    def set_langs(self, langs):
        self.calls.append(("set_langs", list(langs)))

    def set_online(self, online):
        self.calls.append(("set_online", online))

    def set_read_aloud(self, on):
        self.calls.append(("set_read_aloud", on))

    def set_glossary(self, g):
        self.calls.append(("set_glossary", len(g.rules)))

    def shutdown(self):
        pass


class FakePhrases:
    def __init__(self, home: Path) -> None:
        self.home = home
        self.items = [FakePhrase(f"p{i}", ko, {"mn": f"mn{i}", "zh": f"zh{i}", "en": f"en{i}"}, False)
                      for i, ko in enumerate(["떠들지 마세요.", "집중하세요.", "이해됐나요?", "질문 있나요?",
                                              "질문 없으면 넘어갈게요."], start=1)]

    def load_all(self):
        return list(self.items)

    def add_custom(self, ko, texts):
        p = FakePhrase(f"c{len(self.items)}", ko, dict(texts), True)
        self.items.append(p)
        return p

    def remove_custom(self, key):
        self.items = [p for p in self.items if p.key != key]

    def audio_path(self, phrase, lang):
        return self.home / "phrases" / f"{phrase.key}_{lang}.mp3"


class FakeConfig:
    def __init__(self) -> None:
        self.saved_settings = 0
        self.saved_glossary = 0

    def save_settings(self, s):
        self.saved_settings += 1

    def save_glossary(self, g):
        self.saved_glossary += 1

    def load_glossary(self):
        return Glossary()


class FakeMic:
    @staticmethod
    def list_devices():
        return ["USB 핀마이크", "내장 마이크"]


class FakeSpeaker:
    name = "fake"

    def synth(self, text, lang):
        return b"ID3" + text.encode()


def _all_text(widget) -> list[str]:
    out = []
    for w in widget.winfo_children():
        try:
            t = w.cget("text")
            if isinstance(t, str) and t:
                out.append(t)
        except (tkinter.TclError, ValueError, AttributeError):
            pass
        out.extend(_all_text(w))
    return out


def _count(widget) -> int:
    return sum(1 + _count(w) for w in widget.winfo_children())


@pytest.fixture
def app(tmp_path):
    from sukpago.ui.app import App

    pipe, cfg = FakePipeline(), FakeConfig()
    glossary = Glossary()
    glossary.add("노트북 에램", "NotebookLM")
    try:
        a = App(pipe, FakeSettings(), FakePhrases(tmp_path), cfg, mic_api=FakeMic(), speaker=FakeSpeaker(),
                glossary=glossary, memory_mb=lambda: 614.0)
    except tkinter.TclError as e:
        pytest.skip(f"화면 없음: {e}")
    a.withdraw()
    yield a, pipe, cfg
    try:
        a.destroy()
    except tkinter.TclError:
        pass


def _pump(a, times: int = 3) -> None:
    import time

    for _ in range(times):
        a.update()
        time.sleep(0.06)
    a.update()


def test_app_draws_events(app):
    a, pipe, _ = app
    for ev in [Partial("오늘은 광합성에"), Final(1, "오늘은 광합성에 대해 배울 거예요."),
               Translation(1, "mn", "Өнөөдөр бид фотосинтез"), Translation(1, "zh", "今天我们将学习光合作用。"),
               MicLevel(-20.0, 0.0, "ok"), Status("fallback", "오프라인으로 전환됨 (오류)")]:
        pipe.events.put(ev)
    _pump(a)
    texts = _all_text(a)
    assert "오늘은 광합성에 대해 배울 거예요." in texts
    assert "今天我们将学习光合作用。" in texts
    assert "오프라인으로 전환됨 (오류)" in texts
    assert a.status_label.cget("text") == "온라인 · 인식 Zipformer · 번역 MyMemory · 메모리 0.6GB"
    assert len(a.phrase_buttons) == 5
    assert "NotebookLM" in texts
    assert _count(a) > 50


def test_app_controls(app):
    a, pipe, cfg = app
    a.toggle_lang("en")
    assert a.settings.langs == ["mn", "zh", "en"]
    a.toggle_lang("mn")
    a.toggle_lang("zh")
    a.toggle_lang("en")  # 마지막 하나는 끌 수 없다
    assert a.settings.langs == ["en"]
    a.set_online(False)
    assert ("set_online", False) in pipe.calls
    assert a.status_label.cget("text").startswith("오프라인")
    a.toggle_live()
    assert pipe.live and a.live_button.cget("text").endswith("멈추기")
    a.toggle_live()
    assert not pipe.live
    a.direct_entry.insert(0, "가" * 501)
    a.submit_direct()
    assert "500자" in a.direct_hint.cget("text")
    a.direct_entry.delete(0, "end")
    a.direct_entry.insert(0, "안녕하세요")
    a.submit_direct()
    _pump(a)
    assert ("submit_text", "안녕하세요") in pipe.calls
    a.save_settings()
    assert cfg.saved_settings >= 1


def test_custom_phrase_and_glossary(app, tmp_path):
    a, pipe, cfg = app
    a.custom_panel.text_entry.insert(0, "휴대폰 넣어 주세요.")
    a.custom_panel.add()
    for _ in range(40):
        _pump(a, 1)
        if not a.custom_panel.busy:
            break
    assert len(a.phrase_buttons) == 6
    assert (tmp_path / "phrases" / "c5_mn.mp3").exists()
    a.glossary_panel.wrong_entry.insert(0, "한강 리스크")
    a.glossary_panel.right_entry.insert(0, "할루시네이션 리스크")
    a.glossary_panel.add()
    assert cfg.saved_glossary == 1 and ("set_glossary", 2) in pipe.calls


def test_display_window(app):
    a, pipe, _ = app
    d = a.open_display()
    d.withdraw()
    for seq in range(1, 8):
        pipe.events.put(Final(seq, f"문장 {seq}"))
        pipe.events.put(Translation(seq, "mn", f"mn {seq}"))
        pipe.events.put(Translation(seq, "zh", f"中文 {seq}"))
    _pump(a)
    assert d.count == 7
    content = d.text.get("1.0", "end")
    assert "MN mn 1" in content and "ZH 中文 7" in content
    assert content.index("mn 3") < content.index("中文 3") < content.index("mn 4")
    d.select(3)
    _pump(a, 1)
    assert d.selected == 3
    assert ("speak", {"mn": "mn 3", "zh": "中文 3"}) in pipe.calls
    d.to_latest()
    assert d.selected is None
    d.step_size(+1)
    assert d.font_px == 60 and a.settings.display_font_px == 60
    d.set_langs(["zh"])
    assert "mn 1" not in d.text.get("1.0", "end")


def test_display_late_translation_and_limit(app):
    a, pipe, _ = app
    d = a.open_display()
    d.withdraw()
    d.add_final(1, "a")
    d.add_final(2, "b")
    d.add_translation(2, "mn", "second")
    d.add_translation(1, "mn", "first")  # 늦게 온 번역도 제자리에 들어간다
    content = d.text.get("1.0", "end")
    assert content.index("first") < content.index("second")
    for seq in range(3, 510):
        d.add_final(seq, "x")
        d.add_translation(seq, "mn", f"t{seq}")
    assert d.count == 500
    content = d.text.get("1.0", "end")
    assert "first" not in content and "t509" in content
