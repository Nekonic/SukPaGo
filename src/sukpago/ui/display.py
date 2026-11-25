"""번역 전용 창: 번역문만 크게, 전체 기록을 스크롤로. 프로젝터나 두 번째 모니터용."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

import customtkinter as ctk

from ..languages import TARGET_ORDER
from . import theme
from .layout import clamp_font, ordered_texts, step_font


class DisplayWindow(ctk.CTkToplevel):
    def __init__(self, master, *, font_px: int, geometry: str | None,
                 on_font_change: Callable[[int], None], on_close: Callable[[str], None]) -> None:
        super().__init__(master, fg_color=theme.BG)
        self.title("석파고 · 번역 창")
        self.geometry(geometry or "1280x720")
        self.attributes("-topmost", True)
        self._font_px = clamp_font(font_px)
        self._on_font_change = on_font_change
        self._on_close = on_close
        self._history: list[dict[str, str]] = []
        self._langs: list[str] = []

        bar = ctk.CTkFrame(self, fg_color=theme.BG)
        bar.pack(side="top", fill="x", padx=8, pady=(4, 0))
        for label, delta in (("A+", 1), ("A−", -1)):
            ctk.CTkButton(bar, text=label, width=44, height=36, fg_color=theme.BUTTON,
                          hover_color=theme.BUTTON_HOVER, text_color=theme.TEXT, border_width=1,
                          border_color=theme.BORDER,
                          command=lambda d=delta: self._step(d)).pack(side="right", padx=(4, 0))

        self.text = tk.Text(self, wrap="word", bd=0, highlightthickness=0, padx=8, pady=0,
                            bg=theme.BG, fg=theme.TEXT, cursor="arrow", spacing1=0, spacing3=0)
        self.text.pack(side="top", fill="both", expand=True)
        self._configure_tags()
        self.protocol("WM_DELETE_WINDOW", self.close)

    def _configure_tags(self) -> None:
        for lang in TARGET_ORDER:
            self.text.tag_configure(lang, font=(theme.family_for(lang), self._font_px, "bold"))

    def _step(self, delta: int) -> None:
        self._font_px = step_font(self._font_px, delta)
        self._configure_tags()
        self._on_font_change(self._font_px)

    @property
    def font_px(self) -> int:
        return self._font_px

    def show(self, history: list[dict[str, str]], langs: list[str]) -> None:
        """기록 전체를 다시 그린다. 맨 아래를 보고 있을 때만 맨 아래로 따라간다."""
        follow = self.text.yview()[1] >= 0.999
        self._history, self._langs = history, langs
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        for texts in history:
            for lang, line in ordered_texts(texts, langs, TARGET_ORDER):
                self.text.insert("end", line + "\n", lang)
        self.text.configure(state="disabled")
        if follow:
            self.text.see("end")

    def close(self) -> None:
        self._on_close(self.geometry())
        self.destroy()
