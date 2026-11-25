"""용어 고치기 창: "인식된 말 → 바꿀 말" 목록을 추가하고 지운다."""

from __future__ import annotations

from collections.abc import Callable

import customtkinter as ctk

from ..text.glossary import Glossary
from . import theme


class GlossaryWindow(ctk.CTkToplevel):
    def __init__(self, master, glossary: Glossary, on_change: Callable[[Glossary], None]) -> None:
        super().__init__(master, fg_color=theme.BG)
        self.title("용어 고치기")
        self.geometry("520x420")
        self.attributes("-topmost", True)
        self._glossary = glossary
        self._on_change = on_change

        form = ctk.CTkFrame(self, fg_color=theme.BG)
        form.pack(fill="x", padx=12, pady=12)
        self.wrong = ctk.CTkEntry(form, placeholder_text="인식된 말 (예: 노트북 에램)")
        self.right = ctk.CTkEntry(form, placeholder_text="바꿀 말 (예: NotebookLM)")
        self.wrong.pack(side="left", fill="x", expand=True)
        self.right.pack(side="left", fill="x", expand=True, padx=6)
        ctk.CTkButton(form, text="추가", width=60, fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
                      command=self._add).pack(side="left")
        self.right.bind("<Return>", lambda _e: self._add())

        self.rows = ctk.CTkScrollableFrame(self, fg_color=theme.BG)
        self.rows.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self._render()

    def _render(self) -> None:
        for w in self.rows.winfo_children():
            w.destroy()
        for rule in self._glossary.rules:
            row = ctk.CTkFrame(self.rows, fg_color=theme.BG)
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=f"{rule.wrong}  →  {rule.right}", text_color=theme.TEXT,
                         anchor="w").pack(side="left", fill="x", expand=True)
            ctk.CTkButton(row, text="삭제", width=50, fg_color=theme.BUTTON, text_color=theme.TEXT,
                          hover_color=theme.BUTTON_HOVER, border_width=1, border_color=theme.BORDER,
                          command=lambda w=rule.wrong: self._remove(w)).pack(side="right")

    def _add(self) -> None:
        try:
            self._glossary.add(self.wrong.get(), self.right.get())
        except ValueError:
            return
        self.wrong.delete(0, "end")
        self.right.delete(0, "end")
        self._changed()

    def _remove(self, wrong: str) -> None:
        self._glossary.remove(wrong)
        self._changed()

    def _changed(self) -> None:
        self._on_change(self._glossary)
        self._render()
