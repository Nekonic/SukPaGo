"""메인 창.

위에서부터: 머리말, 설정 줄, 실시간 듣기, 현재 문장, 패널 3개, 빠른 안내 버튼, 직접 입력, 상태 표시줄.
파이프라인 이벤트는 50ms마다 꺼내 그린다. 오래 걸리는 일(번역, 음성 합성, 재생 준비)은 작업 스레드에서 하고,
작업 스레드는 화면을 직접 건드리지 않고 `post`로 Tk 스레드에 일을 넘긴다.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from collections import OrderedDict
from typing import TYPE_CHECKING, Any, Callable

import customtkinter as ctk

from ..languages import TARGET_ORDER
from ..languages import get as get_lang
from . import layout, theme
from .panels import CustomPhrasePanel, GlossaryPanel, MicPanel, Segmented

if TYPE_CHECKING:  # 다른 작업(W1, W5)의 모듈. 실행할 때는 가져오지 않는다.
    from ..config import Settings
    from ..pipeline import Pipeline
    from .display import DisplayWindow

POLL_MS = 50
MEM_MS = 2000
SAVE_DELAY_MS = 400
MESSAGE_MS = 8000
MAX_HISTORY = 500
MEM_LIMIT_MB = 2048
CURRENT_PX = 36          # 현재 문장 번역 글자 크기(약 28pt)
PARTIAL_HINT = "버튼을 누르면 마이크로 강의를 듣기 시작합니다."

_STICKY = {"quota", "mic_error"}
_MESSAGE_COLOR = {"mic_error": theme.RED, "fallback": theme.ORANGE, "quota": theme.ORANGE,
                  "tts_error": theme.ORANGE, "audio_error": theme.ORANGE, "delay": theme.ORANGE,
                  "info": theme.MUTED}


def _font(size: int = 15, weight: str = "normal", family: str | None = None) -> ctk.CTkFont:
    return ctk.CTkFont(family=family or theme.FONT_KO, size=size, weight=weight)


def _memory_mb() -> float:
    try:
        import psutil

        return psutil.Process().memory_info().rss / (1024 * 1024)
    except Exception:
        return 0.0


class App(ctk.CTk):
    def __init__(self, pipeline: "Pipeline", settings: "Settings", phrases_api: Any = None,
                 config_api: Any = None, *, mic_api: Any = None, speaker: Any = None,
                 glossary: Any = None, asr_name: str = "Zipformer",
                 memory_mb: Callable[[], float] = _memory_mb) -> None:
        ctk.set_appearance_mode("light")
        super().__init__(fg_color=theme.BG)
        if phrases_api is None:
            from .. import phrases as phrases_api  # noqa: PLC0415 (W1 모듈, 조립할 때 있음)
        if config_api is None:
            from .. import config as config_api  # noqa: PLC0415
        if mic_api is None:
            try:
                from ..asr import mic as mic_api  # noqa: PLC0415
            except Exception:
                mic_api = None
        self.pipeline = pipeline
        self.settings = settings
        self.phrases_api = phrases_api
        self.config_api = config_api
        self.mic_api = mic_api
        self.speaker = speaker
        self.glossary = glossary if glossary is not None else config_api.load_glossary()
        self._asr_name = asr_name
        self._memory_mb = memory_mb

        self._ui_calls: queue.Queue[Callable[[], None]] = queue.Queue()
        self._afters: dict[str, str] = {}
        self._history: OrderedDict[int, tuple[str, dict[str, str]]] = OrderedDict()
        self._current: int | None = None
        self._local_seq = 0           # 빠른 안내 문장은 음수 seq로 기록한다
        self._engine: str | None = None
        self._reason: str | None = None
        self._mem = 0.0
        self._sticky_message: tuple[str, str] | None = None
        self.display: "DisplayWindow | None" = None
        self._closing = False

        self.title("석파고 SukPaGo")
        self.minsize(960, 720)
        self.geometry(getattr(settings, "main_geometry", None) or "1180x920")
        self.attributes("-topmost", bool(settings.pinned))
        self.protocol("WM_DELETE_WINDOW", self.close)

        body = ctk.CTkFrame(self, fg_color=theme.BG)
        body.pack(fill="both", expand=True, padx=16, pady=12)
        body.columnconfigure(0, weight=1)
        self.body = body
        self._build_header(body, 0)
        self._build_settings(body, 1)
        self._build_live(body, 2)
        self._build_current(body, 3)
        self._build_panels(body, 4)
        self._build_phrases(body, 5)
        self._build_direct(body, 6)
        self._build_status(body, 7)
        body.rowconfigure(4, weight=1)

        self._render_toggles()
        self._render_current()
        self._render_live()
        self._render_status()
        self._schedule("poll", POLL_MS, self._poll)
        self._update_memory()

    # ---------- 화면 구성 ----------

    def _build_header(self, parent, row: int) -> None:
        head = ctk.CTkFrame(parent, fg_color="transparent")
        head.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        head.columnconfigure(1, weight=1)
        title = ctk.CTkFrame(head, fg_color="transparent")
        title.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(title, text="석파고", font=_font(26, "bold"), text_color=theme.INK).pack(side="left")
        ctk.CTkLabel(title, text="SukPaGo", font=_font(16, family=theme.FONT_LATIN),
                     text_color=theme.MUTED).pack(side="left", padx=(10, 0), pady=(6, 0))

        right = ctk.CTkFrame(head, fg_color="transparent")
        right.grid(row=0, column=2, sticky="e")
        self.mode_pill = ctk.CTkLabel(right, text="", height=32, corner_radius=16, font=_font(14, "bold"))
        self.mode_pill.pack(side="left", padx=(0, 10))
        self.display_button = ctk.CTkButton(
            right, text="🖥  번역 창 띄우기", command=self.open_display, height=40, corner_radius=10,
            fg_color=theme.BG, hover_color=theme.HOVER_BG, text_color=theme.INK, border_width=1,
            border_color=theme.BORDER_STRONG, font=_font(15, "bold"))
        self.display_button.pack(side="left", padx=(0, 10))
        self.pin_button = ctk.CTkButton(right, text="📌", width=40, height=40, corner_radius=10,
                                        command=self.toggle_pin, border_width=1, font=_font(16))
        self.pin_button.pack(side="left")

    def _card(self, parent, row: int, *, white: bool = False, pady=(0, 8)) -> ctk.CTkFrame:
        card = ctk.CTkFrame(parent, corner_radius=14, border_width=1,
                            fg_color=theme.BG if white else theme.CARD,
                            border_color=theme.BORDER_STRONG if white else theme.BORDER)
        card.grid(row=row, column=0, sticky="nsew", pady=pady)
        return card

    def _divider(self, parent) -> ctk.CTkFrame:
        return ctk.CTkFrame(parent, width=1, height=30, fg_color=theme.BORDER, corner_radius=0)

    def _build_settings(self, parent, row: int) -> None:
        card = self._card(parent, row)
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=10)
        self.mode_button = Segmented(inner, ["온라인", "오프라인"], self._on_mode, height=36,
                                     colors={"온라인": theme.ACCENT, "오프라인": theme.ORANGE})
        self.mode_button.pack(side="left")
        self._divider(inner).pack(side="left", padx=12)
        self.lang_buttons: dict[str, ctk.CTkButton] = {}
        for lang in TARGET_ORDER:
            b = ctk.CTkButton(inner, text="", height=40, corner_radius=20, border_width=1,
                              font=_font(15, "bold"), command=lambda x=lang: self.toggle_lang(x))
            b.pack(side="left", padx=(0, 8))
            self.lang_buttons[lang] = b
        self._divider(inner).pack(side="left", padx=(4, 12))
        self.read_switch = ctk.CTkSwitch(
            inner, text="실시간 읽기", command=self._on_read_aloud, font=_font(15, "bold"),
            text_color=theme.INK, progress_color=theme.ACCENT, fg_color=theme.INPUT_BORDER,
            button_color="#FFFFFF", button_hover_color="#FFFFFF", switch_width=40, switch_height=22)
        self.read_switch.pack(side="left")

    def _build_live(self, parent, row: int) -> None:
        card = self._card(parent, row)
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=10)
        inner.columnconfigure(2, weight=1)
        self.live_button = ctk.CTkButton(inner, text="", command=self.toggle_live, height=48, corner_radius=24,
                                         text_color="#FFFFFF", font=_font(16, "bold"), width=170)
        self.live_button.grid(row=0, column=0)
        self.level_canvas = tk.Canvas(inner, width=34, height=24, bg=theme.CARD, highlightthickness=0, bd=0)
        self.level_canvas.grid(row=0, column=1, padx=12)
        self.partial_label = ctk.CTkLabel(inner, text=PARTIAL_HINT, font=_font(18), text_color=theme.MUTED,
                                          anchor="w", justify="left")
        self.partial_label.grid(row=0, column=2, sticky="ew")
        inner.bind("<Configure>", lambda e: self.partial_label.configure(wraplength=max(200, e.width - 260)))

    def _build_current(self, parent, row: int) -> None:
        card = self._card(parent, row, white=True)
        self.current_frame = ctk.CTkFrame(card, fg_color="transparent")
        self.current_frame.pack(fill="x", padx=20, pady=14)
        self.current_frame.columnconfigure(1, weight=1)
        self._current_wrap = 700
        card.bind("<Configure>", self._on_current_resize)

    def _build_panels(self, parent, row: int) -> None:
        row_frame = ctk.CTkFrame(parent, fg_color="transparent")
        row_frame.grid(row=row, column=0, sticky="nsew", pady=(0, 8))
        row_frame.columnconfigure(0, weight=4, uniform="p")
        row_frame.columnconfigure(1, weight=3, uniform="p")
        row_frame.columnconfigure(2, weight=3, uniform="p")
        row_frame.rowconfigure(0, weight=1)
        self.glossary_panel = GlossaryPanel(row_frame, self.glossary, config_api=self.config_api,
                                            pipeline=self.pipeline, notify=self.notify)
        self.glossary_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self.custom_panel = CustomPhrasePanel(
            row_frame, pipeline=self.pipeline, phrases_api=self.phrases_api, settings=self.settings,
            post=self.post, speaker=self.speaker, on_change=self._render_phrases, notify=self.notify)
        self.custom_panel.grid(row=0, column=1, sticky="nsew", padx=6)
        self.mic_panel = MicPanel(row_frame, mic_api=self.mic_api, settings=self.settings,
                                  on_device=self._on_mic_device)
        self.mic_panel.grid(row=0, column=2, sticky="nsew", padx=(6, 0))

    def _build_phrases(self, parent, row: int) -> None:
        self.phrase_frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.phrase_frame.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        self.phrase_buttons: list[ctk.CTkButton] = []
        self._render_phrases()

    def _build_direct(self, parent, row: int) -> None:
        box = ctk.CTkFrame(parent, fg_color="transparent")
        box.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        box.columnconfigure(0, weight=1)
        top = ctk.CTkFrame(box, fg_color="transparent")
        top.grid(row=0, column=0, columnspan=2, sticky="ew")
        ctk.CTkLabel(top, text="한국어 직접 입력", font=_font(14, "bold"), text_color=theme.MUTED,
                     height=20).pack(side="left")
        self.direct_hint = ctk.CTkLabel(top, text="", font=_font(13), text_color=theme.ORANGE, height=20)
        self.direct_hint.pack(side="left", padx=10)
        self.direct_entry = ctk.CTkEntry(
            box, placeholder_text="번역할 문장을 입력하고 Enter", height=46, corner_radius=10, border_width=1,
            border_color=theme.INPUT_BORDER, fg_color=theme.BG, text_color=theme.INK,
            placeholder_text_color=theme.MUTED, font=_font(17))
        self.direct_entry.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self.direct_entry.bind("<Return>", lambda _e: self.submit_direct())
        ctk.CTkButton(box, text="번역", command=self.submit_direct, width=96, height=46, corner_radius=10,
                      fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER, text_color="#FFFFFF",
                      font=_font(16, "bold")).grid(row=1, column=1, padx=(10, 0), pady=(4, 0))

    def _build_status(self, parent, row: int) -> None:
        card = ctk.CTkFrame(parent, corner_radius=10, border_width=1, fg_color=theme.CARD,
                            border_color=theme.BORDER)
        card.grid(row=row, column=0, sticky="ew")
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=6)
        inner.columnconfigure(1, weight=1)
        self.status_label = ctk.CTkLabel(inner, text="", font=_font(14), text_color=theme.MUTED, anchor="w")
        self.status_label.grid(row=0, column=0, sticky="w")
        self.message_label = ctk.CTkLabel(inner, text="", font=_font(14, "bold"), text_color=theme.MUTED,
                                          anchor="e")
        self.message_label.grid(row=0, column=1, sticky="e", padx=(12, 12))
        self.mem_bar = ctk.CTkProgressBar(inner, width=110, height=8, corner_radius=4, fg_color=theme.DIVIDER,
                                          progress_color=theme.GREEN)
        self.mem_bar.grid(row=0, column=2, sticky="e")
        self.mem_bar.set(0)

    # ---------- 그리기 ----------

    def _render_toggles(self) -> None:
        online = bool(self.settings.online)
        self.mode_button.set("온라인" if online else "오프라인")
        if online:
            self.mode_pill.configure(text="  온라인 · 인터넷 사용 중  ", fg_color=theme.GREEN_SOFT,
                                     text_color=theme.GREEN)
        else:
            self.mode_pill.configure(text="  오프라인 · 인터넷 없이 동작  ", fg_color=theme.ORANGE_SOFT,
                                     text_color=theme.ORANGE)
        for lang, b in self.lang_buttons.items():
            on = lang in self.settings.langs
            mark = "✓" if on else "○"
            b.configure(text=f"{mark}  {get_lang(lang).name_ko}  {theme.LANG_CODES[lang]}",
                        fg_color=theme.ACCENT_SOFT if on else theme.BG,
                        hover_color=theme.ACCENT_SOFT if on else theme.HOVER_BG,
                        text_color=theme.ACCENT_INK if on else theme.OFF_INK,
                        border_color=theme.ACCENT if on else theme.BORDER_STRONG)
        if self.settings.read_aloud:
            self.read_switch.select()
        else:
            self.read_switch.deselect()
        pinned = bool(self.settings.pinned)
        self.pin_button.configure(fg_color=theme.ACCENT_SOFT if pinned else theme.BG,
                                  hover_color=theme.ACCENT_SOFT if pinned else theme.HOVER_BG,
                                  text_color=theme.ACCENT_INK if pinned else theme.OFF_INK,
                                  border_color=theme.ACCENT if pinned else theme.BORDER_STRONG)

    def _render_live(self) -> None:
        live = bool(getattr(self.pipeline, "live", False))
        if live:
            self.live_button.configure(text="🎤  듣는 중 · 멈추기", fg_color=theme.RED, hover_color=theme.RED_HOVER)
        else:
            self.live_button.configure(text="🎤  실시간 시작", fg_color=theme.ACCENT,
                                       hover_color=theme.ACCENT_HOVER)
            if self.partial_label.cget("text") == "":
                self.partial_label.configure(text=PARTIAL_HINT)
            self._draw_level(None)

    def _draw_level(self, fraction: float | None) -> None:
        c = self.level_canvas
        c.delete("all")
        if fraction is None:
            return
        pattern = (0.45, 0.85, 0.6, 1.0, 0.35)
        for i, p in enumerate(pattern):
            h = max(3, round(24 * min(1.0, fraction * 1.2) * p))
            x = i * 7
            c.create_rectangle(x, 24 - h, x + 4, 24, fill=theme.ACCENT, width=0)

    def _render_current(self) -> None:
        for w in self.current_frame.winfo_children():
            w.destroy()
        self.current_text_labels: dict[str, ctk.CTkLabel] = {}
        if self._current is None or self._current not in self._history:
            ko, texts = "", {}
        else:
            ko, texts = self._history[self._current]
        chip = dict(height=26, corner_radius=6, font=_font(13, "bold", theme.FONT_LATIN), width=40)
        ctk.CTkLabel(self.current_frame, text="KO", fg_color=theme.CHIP, text_color=theme.SUBTLE, **chip).grid(
            row=0, column=0, sticky="nw", pady=(2, 8))
        self.current_ko_label = ctk.CTkLabel(
            self.current_frame, text=ko or "확정된 문장이 여기에 크게 나옵니다.", font=_font(20),
            text_color=theme.SUBTLE if ko else theme.MUTED, anchor="w", justify="left",
            wraplength=self._current_wrap)
        self.current_ko_label.grid(row=0, column=1, columnspan=2, sticky="ew", padx=(12, 0), pady=(0, 8))
        r = 1
        for lang in TARGET_ORDER:
            if lang not in self.settings.langs:
                continue
            ctk.CTkFrame(self.current_frame, height=1, fg_color=theme.DIVIDER, corner_radius=0).grid(
                row=r, column=0, columnspan=3, sticky="ew", pady=(2, 8))
            text = texts.get(lang, "")
            ctk.CTkLabel(self.current_frame, text=theme.LANG_CODES[lang], fg_color=theme.ACCENT_SOFT,
                         text_color=theme.CODE_INK, **chip).grid(row=r + 1, column=0, sticky="nw", pady=(10, 8))
            lbl = ctk.CTkLabel(self.current_frame, text=text or ("…" if ko else ""), anchor="w", justify="left",
                               font=_font(CURRENT_PX, "bold", theme.family_for(lang)), text_color=theme.TEXT,
                               wraplength=self._current_wrap)
            lbl.grid(row=r + 1, column=1, sticky="ew", padx=(14, 10), pady=(0, 8))
            self.current_text_labels[lang] = lbl
            ctk.CTkButton(self.current_frame, text="🔊", width=44, height=44, corner_radius=12,
                          fg_color=theme.BG, hover_color=theme.HOVER_BG, text_color=theme.INK, border_width=1,
                          border_color=theme.BORDER_STRONG, font=_font(18),
                          state="normal" if text else "disabled",
                          command=lambda x=lang: self.replay(x)).grid(row=r + 1, column=2, sticky="ne",
                                                                      pady=(2, 8))
            r += 2

    def _on_current_resize(self, event) -> None:
        wrap = max(300, event.width - 160)
        if abs(wrap - self._current_wrap) < 8:
            return
        self._current_wrap = wrap
        if not hasattr(self, "current_text_labels"):
            return
        self.current_ko_label.configure(wraplength=wrap)
        for lbl in self.current_text_labels.values():
            lbl.configure(wraplength=wrap)

    def _render_phrases(self) -> None:
        for w in self.phrase_frame.winfo_children():
            w.destroy()
        self.phrase_buttons = []
        try:
            phrases = list(self.phrases_api.load_all())
        except Exception:
            phrases = []
        cols = max(5, min(6, len(phrases)))   # 6개까지는 한 줄, 그 뒤로는 6개씩 줄을 바꾼다
        for c in range(6):
            self.phrase_frame.columnconfigure(c, weight=1 if c < cols else 0, uniform="q" if c < cols else "")
        for i, p in enumerate(phrases):
            r, c = divmod(i, cols)
            b = ctk.CTkButton(self.phrase_frame, text=p.ko, command=lambda x=p: self.play_phrase(x), height=48,
                              corner_radius=12, fg_color=theme.CARD, hover_color=theme.DIVIDER,
                              text_color=theme.INK, border_width=1,
                              border_color=theme.GREEN_BORDER if p.custom else theme.BORDER_STRONG,
                              font=_font(16, "bold"))
            b.grid(row=r, column=c, sticky="ew", padx=(0 if c == 0 else 4, 0 if c == cols - 1 else 4),
                   pady=(0, 6))
            if p.custom:
                badge = ctk.CTkLabel(b, text="내 문장", height=18, corner_radius=6, fg_color=theme.GREEN_SOFT,
                                     text_color=theme.GREEN, font=_font(11, "bold"))
                badge.place(relx=1.0, x=-8, y=6, anchor="ne")
                badge.bind("<Button-1>", lambda _e, x=p: self.play_phrase(x))
            self.phrase_buttons.append(b)

    def _render_status(self) -> None:
        text = layout.status_text(bool(self.settings.online), self._engine, self._reason, self._mem,
                                  asr=self._asr_name)
        self.status_label.configure(text=text)
        self.mem_bar.set(min(1.0, self._mem / MEM_LIMIT_MB))
        self.mem_bar.configure(progress_color=theme.ORANGE if self._mem > MEM_LIMIT_MB * 0.9 else theme.GREEN)

    # ---------- 알림 ----------

    def notify(self, kind: str, message: str) -> None:
        """상태 표시줄 오른쪽에 알림을 띄운다. 한도 초과·마이크 오류는 계속 남긴다."""
        color = _MESSAGE_COLOR.get(kind, theme.MUTED)
        self.message_label.configure(text=message, text_color=color)
        self._cancel("message")
        if kind in _STICKY:
            self._sticky_message = (message, color)
        else:
            self._schedule("message", MESSAGE_MS, self._restore_message)

    def _restore_message(self) -> None:
        if self._sticky_message:
            msg, color = self._sticky_message
            self.message_label.configure(text=msg, text_color=color)
        else:
            self.message_label.configure(text="")

    def post(self, fn: Callable[[], None]) -> None:
        """작업 스레드에서 불러도 된다. fn은 다음 폴링 때 Tk 스레드에서 실행된다."""
        self._ui_calls.put(fn)

    # ---------- 이벤트 ----------

    def _poll(self) -> None:
        for _ in range(500):
            try:
                ev = self.pipeline.events.get_nowait()
            except queue.Empty:
                break
            try:
                self.handle_event(ev)
            except Exception as e:  # 한 이벤트 때문에 화면 갱신이 멈추지 않게 한다
                self.notify("info", f"화면 갱신 오류: {e}")
        for _ in range(100):
            try:
                fn = self._ui_calls.get_nowait()
            except queue.Empty:
                break
            try:
                fn()
            except Exception as e:
                self.notify("info", f"화면 갱신 오류: {e}")
        self._schedule("poll", POLL_MS, self._poll)

    def handle_event(self, ev: Any) -> None:
        """파이프라인 이벤트 하나를 그린다. 클래스 이름으로 구분한다(pipeline 모듈을 가져오지 않음)."""
        kind = type(ev).__name__
        if kind == "Partial":
            self.partial_label.configure(text=ev.text or "", text_color=theme.MUTED)
        elif kind == "Final":
            self._add_final(ev.seq, ev.ko)
            if getattr(ev, "source", "live") == "live":
                self.partial_label.configure(text="")
        elif kind == "Translation":
            self._engine, self._reason = ev.engine, ev.reason
            self._add_translation(ev.seq, ev.lang, ev.text)
            self._render_status()
        elif kind == "Status":
            self._on_status(ev.kind, ev.message)
        elif kind == "MicLevel":
            self.mic_panel.update_level(ev.dbfs, ev.clip_ratio, ev.state)
            if getattr(self.pipeline, "live", False):
                self._draw_level(layout.mic_bar_fraction(ev.dbfs))

    def _on_status(self, kind: str, message: str) -> None:
        if kind == "mic_error":
            self._render_live()
            self.live_button.configure(state="disabled")
            self.mic_panel.reset_level()
        self.notify(kind, message)

    def _add_final(self, seq: int, ko: str) -> None:
        self._history[seq] = (ko, {})
        while len(self._history) > MAX_HISTORY:
            self._history.popitem(last=False)
        self._current = seq
        self._render_current()
        if self.display is not None:
            self.display.add_final(seq, ko)

    def _add_translation(self, seq: int, lang: str, text: str) -> None:
        if seq not in self._history:
            self._add_final(seq, "")
        self._history[seq][1][lang] = text
        if seq == self._current:
            self._render_current()
        if self.display is not None:
            self.display.add_translation(seq, lang, text)

    # ---------- 조작 ----------

    def toggle_lang(self, lang: str) -> None:
        langs = list(self.settings.langs)
        if lang in langs:
            if len(langs) == 1:
                self.notify("info", "언어는 하나 이상 켜야 합니다.")
                return
            langs.remove(lang)
        else:
            langs.append(lang)
        self.settings.langs = [x for x in TARGET_ORDER if x in langs]
        self.pipeline.set_langs(list(self.settings.langs))
        if self.display is not None:
            self.display.set_langs(list(self.settings.langs))
        self._render_toggles()
        self._render_current()
        self._save_soon()

    def _on_mode(self, value: str) -> None:
        self.set_online(value == "온라인")

    def set_online(self, online: bool) -> None:
        self.settings.online = online
        self.pipeline.set_online(online)
        self._render_toggles()
        self._render_status()
        self._save_soon()

    def _on_read_aloud(self) -> None:
        self.settings.read_aloud = bool(self.read_switch.get())
        self.pipeline.set_read_aloud(self.settings.read_aloud)
        self._save_soon()

    def toggle_pin(self) -> None:
        self.settings.pinned = not self.settings.pinned
        self.attributes("-topmost", self.settings.pinned)
        self._render_toggles()
        self._save_soon()

    def toggle_live(self) -> None:
        if getattr(self.pipeline, "live", False):
            self.pipeline.stop_live()
            self.mic_panel.reset_level()
        else:
            self.pipeline.start_live()
            if getattr(self.pipeline, "live", False):
                self.partial_label.configure(text="")
        self._render_live()

    def _on_mic_device(self, device: str | None) -> None:
        self.live_button.configure(state="normal")
        if self._sticky_message and self._sticky_message[1] == theme.RED:
            self._sticky_message = None
            self._restore_message()
        if getattr(self.pipeline, "live", False):
            self.pipeline.stop_live()
            self.pipeline.start_live()
            self._render_live()
        self._save_soon()

    def replay(self, lang: str) -> None:
        if self._current is None or self._current not in self._history:
            return
        text = self._history[self._current][1].get(lang)
        if text:
            self._background(self.pipeline.speak, {lang: text})

    def play_phrase(self, phrase: Any) -> None:
        """빠른 안내 문장: 저장된 번역을 바로 보여 주고, 소리는 작업 스레드에서 낸다."""
        self._local_seq -= 1
        seq = self._local_seq
        self._add_final(seq, phrase.ko)
        for lang in TARGET_ORDER:
            text = phrase.texts.get(lang)
            if text:
                self._add_translation(seq, lang, text)
        self._background(self.pipeline.play_phrase, phrase)

    def submit_direct(self) -> None:
        text = self.direct_entry.get()
        problem = layout.check_direct_input(text)
        if problem:
            self.direct_hint.configure(text=problem)
            self._schedule("hint", MESSAGE_MS, lambda: self.direct_hint.configure(text=""))
            return
        self.direct_hint.configure(text="")
        self.direct_entry.delete(0, "end")
        self._background(self.pipeline.submit_text, text.strip())

    def open_display(self) -> "DisplayWindow":
        from .display import DisplayWindow  # noqa: PLC0415

        if self.display is not None and self.display.winfo_exists():
            self.display.deiconify()
            self.display.lift()
            return self.display
        self.display = DisplayWindow(self, self.pipeline, self.settings, on_settings_changed=self._save_soon,
                                     on_close=self._on_display_closed, langs=list(self.settings.langs))
        for seq, (ko, texts) in self._history.items():
            self.display.add_final(seq, ko)
            for lang, text in texts.items():
                self.display.add_translation(seq, lang, text)
        return self.display

    def _on_display_closed(self) -> None:
        self.display = None

    # ---------- 저장, 종료 ----------

    def _save_soon(self) -> None:
        self._schedule("save", SAVE_DELAY_MS, self.save_settings)

    def save_settings(self) -> None:
        self._cancel("save")
        try:
            self.config_api.save_settings(self.settings)
        except Exception as e:
            self.notify("info", f"설정을 저장하지 못했습니다: {e}")

    def close(self) -> None:
        if self._closing:
            return
        self._closing = True
        try:
            self.settings.main_geometry = self.geometry()
        except tk.TclError:
            pass
        if self.display is not None:
            try:
                self.display.save_geometry()
            except tk.TclError:
                pass
        self.save_settings()
        self.destroy()

    def destroy(self) -> None:
        for key in list(self._afters):
            self._cancel(key)
        super().destroy()

    # ---------- 도우미 ----------

    def _update_memory(self) -> None:
        self._mem = self._memory_mb()
        self._render_status()
        self._schedule("mem", MEM_MS, self._update_memory)

    def _schedule(self, key: str, ms: int, fn: Callable[[], None]) -> None:
        self._cancel(key)

        def run() -> None:
            self._afters.pop(key, None)
            fn()

        self._afters[key] = self.after(ms, run)

    def _cancel(self, key: str) -> None:
        after_id = self._afters.pop(key, None)
        if after_id is not None:
            try:
                self.after_cancel(after_id)
            except tk.TclError:
                pass

    def _background(self, fn: Callable, *args) -> None:
        """파이프라인 호출을 작업 스레드에서 한다(합성·재생 준비가 Tk를 막지 않게)."""
        def run() -> None:
            try:
                fn(*args)
            except Exception as e:
                self.post(lambda e=e: self.notify("info", f"처리하지 못했습니다: {e}"))

        threading.Thread(target=run, daemon=True).start()
