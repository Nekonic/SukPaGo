"""메인 창: 모드·언어 선택, 실시간 듣기, 현재 문장, 빠른 안내 버튼 5개."""

from __future__ import annotations

import queue
import threading
from typing import TYPE_CHECKING

import customtkinter as ctk

from ..languages import TARGET_ORDER, get
from . import theme
from .display import DisplayWindow
from .glossary import GlossaryWindow
from .layout import MAX_HISTORY, ordered_texts

if TYPE_CHECKING:
    from ..config import Settings
    from ..text.glossary import Glossary

POLL_MS = 50


class App(ctk.CTk):
    def __init__(self, pipeline, settings: Settings, glossary: Glossary, *, phrases_api=None,
                 config_api=None) -> None:
        super().__init__(fg_color=theme.BG)
        if phrases_api is None:
            from .. import phrases as phrases_api
        if config_api is None:
            from .. import config as config_api
        self.pipeline, self.settings, self.glossary = pipeline, settings, glossary
        self._phrases_api, self._config = phrases_api, config_api
        self.history: list[dict[str, str]] = []   # 번역 창 기록 (문장마다 {언어: 번역})
        self._rows: dict[int, dict[str, str]] = {}
        self._current_seq: int | None = None
        self._local_seq = 0
        self.display: DisplayWindow | None = None
        self._sticky_status = False

        ctk.set_appearance_mode("light")
        self.title("석파고 SukPaGo")
        self.geometry(settings.main_geometry or "980x560")
        self.attributes("-topmost", True)
        self._build()
        self.protocol("WM_DELETE_WINDOW", self.quit_app)
        self.after(POLL_MS, self._poll)

    # ---- 화면 만들기 ----

    def _build(self) -> None:
        top = ctk.CTkFrame(self, fg_color=theme.BG)
        top.pack(fill="x", padx=16, pady=(12, 6))
        self.mode = ctk.CTkSegmentedButton(top, values=["온라인", "오프라인"], command=self._set_mode,
                                           selected_color=theme.ACCENT, selected_hover_color=theme.ACCENT_HOVER)
        self.mode.set("온라인" if self.settings.online else "오프라인")
        self.mode.pack(side="left")
        self.lang_vars: dict[str, ctk.BooleanVar] = {}
        for lang in TARGET_ORDER:
            var = ctk.BooleanVar(value=lang in self.settings.langs)
            ctk.CTkCheckBox(top, text=get(lang).name_ko, variable=var, text_color=theme.TEXT,
                            fg_color=theme.ACCENT, command=lambda lg=lang: self._toggle_lang(lg)
                            ).pack(side="left", padx=(16, 0))
            self.lang_vars[lang] = var
        self._plain_button(top, "번역 창", self.open_display).pack(side="right")
        self._plain_button(top, "용어 고치기", self.open_glossary).pack(side="right", padx=(0, 8))

        live = ctk.CTkFrame(self, fg_color=theme.BG)
        live.pack(fill="x", padx=16, pady=6)
        self.live_button = ctk.CTkButton(live, text="🎤 시작", width=120, height=44, command=self.toggle_live,
                                         fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
                                         font=ctk.CTkFont(theme.FONT_KO, 16, "bold"))
        self.live_button.pack(side="left")
        self.partial = ctk.CTkLabel(live, text="", text_color=theme.MUTED, anchor="w",
                                    font=ctk.CTkFont(theme.FONT_KO, 16))
        self.partial.pack(side="left", fill="x", expand=True, padx=12)

        current = ctk.CTkFrame(self, fg_color=theme.BG)
        current.pack(fill="both", expand=True, padx=16, pady=6)
        self.ko = ctk.CTkLabel(current, text="", text_color=theme.TEXT, anchor="w", justify="left",
                               font=ctk.CTkFont(theme.FONT_KO, 20), wraplength=900)
        self.ko.pack(fill="x")
        self.lines: dict[str, ctk.CTkLabel] = {}
        for lang in TARGET_ORDER:
            label = ctk.CTkLabel(current, text="", text_color=theme.TEXT, anchor="w", justify="left",
                                 font=ctk.CTkFont(theme.family_for(lang), 32, "bold"), wraplength=900)
            label.pack(fill="x", pady=(4, 0))
            self.lines[lang] = label
        current.bind("<Configure>", self._rewrap)

        buttons = ctk.CTkFrame(self, fg_color=theme.BG)
        buttons.pack(fill="x", padx=16, pady=6)
        self.phrase_buttons = []
        for phrase in self._phrases_api.load_all():
            b = ctk.CTkButton(buttons, text=phrase.ko, height=52, fg_color=theme.BUTTON,
                              hover_color=theme.BUTTON_HOVER, text_color=theme.TEXT, border_width=1,
                              border_color=theme.BORDER, font=ctk.CTkFont(theme.FONT_KO, 16, "bold"),
                              command=lambda p=phrase: self.say_phrase(p))
            b.pack(side="left", fill="x", expand=True, padx=(0, 6))
            self.phrase_buttons.append(b)

        self.status = ctk.CTkLabel(self, text="", text_color=theme.WARN, anchor="w",
                                   font=ctk.CTkFont(theme.FONT_KO, 13))
        self.status.pack(fill="x", padx=16, pady=(0, 8))

    def _plain_button(self, parent, text, command) -> ctk.CTkButton:
        return ctk.CTkButton(parent, text=text, width=96, height=32, command=command, fg_color=theme.BUTTON,
                             hover_color=theme.BUTTON_HOVER, text_color=theme.TEXT, border_width=1,
                             border_color=theme.BORDER)

    def _rewrap(self, event) -> None:
        width = max(200, event.width - 8)
        for label in (self.ko, *self.lines.values()):
            label.configure(wraplength=width)

    # ---- 조작 ----

    def _set_mode(self, value: str) -> None:
        self.settings.online = value == "온라인"
        self.pipeline.set_online(self.settings.online)
        self._config.save_settings(self.settings)

    def _toggle_lang(self, lang: str) -> None:
        on = [lg for lg in TARGET_ORDER if self.lang_vars[lg].get()]
        if not on:  # 최소 하나는 켜져 있어야 한다
            self.lang_vars[lang].set(True)
            return
        self.settings.langs = on
        self.pipeline.set_langs(on)
        self._config.save_settings(self.settings)
        self._redraw_current()
        self._redraw_display()

    def toggle_live(self) -> None:
        if self.pipeline.live:
            self.live_button.configure(state="disabled")
            threading.Thread(target=self._stop_live, daemon=True).start()
        else:
            self.pipeline.start_live()
            self._sync_live_button()

    def _stop_live(self) -> None:
        self.pipeline.stop_live()
        self.after(0, self._sync_live_button)

    def _sync_live_button(self) -> None:
        if self.pipeline.live:
            self.live_button.configure(text="■ 멈추기", fg_color=theme.RED, hover_color=theme.RED_HOVER,
                                       state="normal")
        else:
            self.live_button.configure(text="🎤 시작", fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
                                       state="normal")
            self.partial.configure(text="")

    def say_phrase(self, phrase) -> None:
        self._local_seq -= 1
        self._new_sentence(self._local_seq, phrase.ko)
        for lang, text in phrase.texts.items():
            self._add_translation(self._local_seq, lang, text)
        self.pipeline.play_phrase(phrase)

    def open_display(self) -> None:
        if self.display is not None and self.display.winfo_exists():
            self.display.lift()
            return
        self.display = DisplayWindow(self, font_px=self.settings.display_font_px,
                                     geometry=self.settings.display_geometry,
                                     on_font_change=self._display_font_changed, on_close=self._display_closed)
        self._redraw_display()

    def _display_font_changed(self, px: int) -> None:
        self.settings.display_font_px = px
        self._config.save_settings(self.settings)

    def _display_closed(self, geometry: str) -> None:
        self.settings.display_geometry = geometry
        self._config.save_settings(self.settings)
        self.display = None

    def open_glossary(self) -> None:
        GlossaryWindow(self, self.glossary, self._glossary_changed)

    def _glossary_changed(self, g) -> None:
        self._config.save_glossary(g)
        self.pipeline.set_glossary(g)

    def quit_app(self) -> None:
        if self.display is not None and self.display.winfo_exists():
            self.settings.display_geometry = self.display.geometry()
        self.settings.main_geometry = self.geometry()
        self._config.save_settings(self.settings)
        self.destroy()

    # ---- 이벤트 그리기 ----

    def _poll(self) -> None:
        try:
            while True:
                self.handle(self.pipeline.events.get_nowait())
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(POLL_MS, self._poll)

    def handle(self, ev) -> None:
        kind = type(ev).__name__
        if kind == "Partial":
            self.partial.configure(text=ev.text)
        elif kind == "Final":
            self.partial.configure(text="")
            if not self._sticky_status:  # 한도 초과 안내는 계속 보이고, 나머지 안내는 다음 문장에서 지운다
                self.status.configure(text="")
            self._new_sentence(ev.seq, ev.ko)
        elif kind == "Translation":
            self._add_translation(ev.seq, ev.lang, ev.text)
        elif kind == "Status":
            self.status.configure(text=ev.message)
            self._sticky_status = ev.kind == "quota"
            if ev.kind == "mic_error":
                self._sync_live_button()

    def _new_sentence(self, seq: int, ko: str) -> None:
        row: dict[str, str] = {}
        self._rows[seq] = row
        self.history.append(row)
        if len(self.history) > MAX_HISTORY:
            old = self.history.pop(0)
            self._rows = {k: v for k, v in self._rows.items() if v is not old}
        self._current_seq = seq
        self.ko.configure(text=ko)
        self._redraw_current()
        self._redraw_display()

    def _add_translation(self, seq: int, lang: str, text: str) -> None:
        row = self._rows.get(seq)
        if row is None:
            return
        row[lang] = text
        if seq == self._current_seq:
            self._redraw_current()
        self._redraw_display()

    def _redraw_current(self) -> None:
        row = self._rows.get(self._current_seq, {}) if self._current_seq is not None else {}
        shown = dict(ordered_texts(row, self.settings.langs, TARGET_ORDER))
        for lang, label in self.lines.items():
            label.configure(text=shown.get(lang, ""))

    def _redraw_display(self) -> None:
        if self.display is not None and self.display.winfo_exists():
            self.display.show(self.history, self.settings.langs)
