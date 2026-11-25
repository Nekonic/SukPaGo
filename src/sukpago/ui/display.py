"""번역 전용 창: 번역문만 크게 보여 주는 별도 창(프로젝터·두 번째 모니터용).

기록은 tk.Text 하나에 태그로 그린다. 문장 500개를 위젯 하나로 처리하므로 가볍다.
문장마다 시작 위치를 표시(mark)해 두고, 번역이 늦게 오면 그 문장 칸만 다시 쓴다.
"""

from __future__ import annotations

import threading
import tkinter as tk
from typing import TYPE_CHECKING, Callable

import customtkinter as ctk

from ..languages import TARGET_ORDER
from . import layout, theme
from .panels import Segmented

if TYPE_CHECKING:  # 다른 작업(W1, W5)의 모듈. 실행할 때는 가져오지 않는다.
    from ..config import Settings
    from ..pipeline import Pipeline

MAX_ITEMS = 500
EDGE = 8          # 창 가장자리 여백
CODE_PX = 12      # 언어 코드 글자 크기


class DisplayWindow(ctk.CTkToplevel):
    def __init__(self, master, pipeline: "Pipeline", settings: "Settings", *,
                 on_settings_changed: Callable[[], None] | None = None,
                 on_close: Callable[[], None] | None = None,
                 langs: list[str] | None = None) -> None:
        super().__init__(master, fg_color=theme.BG)
        self._pipeline = pipeline
        self._settings = settings
        self._on_settings_changed = on_settings_changed or (lambda: None)
        self._on_close = on_close
        self._langs = [lang for lang in TARGET_ORDER if lang in (langs or settings.langs)]
        self._size = layout.clamp_font(getattr(settings, "display_font_px", 52))
        self._prev_scale = float(getattr(settings, "display_prev_scale", 0.75))
        self._pinned = bool(getattr(settings, "display_pinned", True))
        self._items: list[int] = []                 # 문장 seq, 오래된 것부터
        self._data: dict[int, dict[str, str]] = {}  # seq -> {lang: 번역}
        self._style_cache: dict[int, tuple[int, str, str]] = {}
        self._selected: int | None = None
        self._hover: int | None = None

        self.title("석파고 · 번역 창")
        self.minsize(480, 300)
        geo = getattr(settings, "display_geometry", None)
        self.geometry(geo or "1280x720")
        self.attributes("-topmost", self._pinned)
        self.protocol("WM_DELETE_WINDOW", self.close)

        self._build_toolbar()
        self._build_history()
        self._update_pin_button()
        self._update_size_widgets()

    # ---------- 화면 구성 ----------

    def _build_toolbar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color=theme.CARD, corner_radius=0, border_width=0)
        bar.pack(side="top", fill="x")
        ctk.CTkFrame(self, fg_color=theme.BORDER, height=1, corner_radius=0).pack(side="top", fill="x")
        f = lambda size=14, weight="normal": ctk.CTkFont(family=theme.FONT_KO, size=size, weight=weight)  # noqa: E731
        btn = dict(width=40, height=36, corner_radius=10, fg_color=theme.BG, hover_color=theme.HOVER_BG,
                   text_color=theme.INK, border_width=1, border_color=theme.BORDER_STRONG)

        ctk.CTkLabel(bar, text="석파고 · 번역 창", font=f(14, "bold"), text_color=theme.MUTED).pack(
            side="left", padx=(EDGE, 0), pady=2)

        self.pin_button = ctk.CTkButton(bar, text="📌", command=self.toggle_pin, font=f(16), **btn)
        self.pin_button.pack(side="right", padx=(4, EDGE), pady=2)

        self.prev_buttons = Segmented(bar, list(layout.PREV_SCALES), self._on_prev_scale, height=30, size=14)
        self.prev_buttons.pack(side="right", padx=4, pady=2)
        ctk.CTkLabel(bar, text="이전 문장", font=f(14), text_color=theme.MUTED).pack(side="right", padx=(12, 4))

        self.size_label = ctk.CTkLabel(bar, text="", width=52, font=f(15, "bold"), text_color=theme.INK)
        self.size_label.pack(side="right", padx=4)
        ctk.CTkButton(bar, text="A+", command=lambda: self.step_size(+1), font=f(18, "bold"), **btn).pack(
            side="right", padx=4, pady=2)
        self.slider = ctk.CTkSlider(bar, from_=layout.FONT_MIN, to=layout.FONT_MAX,
                                    number_of_steps=(layout.FONT_MAX - layout.FONT_MIN) // 4,
                                    command=self._on_slide, width=180, progress_color=theme.ACCENT,
                                    button_color=theme.ACCENT, button_hover_color=theme.ACCENT_HOVER,
                                    fg_color=theme.BORDER)
        self.slider.pack(side="right", padx=4)
        ctk.CTkButton(bar, text="A−", command=lambda: self.step_size(-1), font=f(15, "bold"), **btn).pack(
            side="right", padx=4, pady=2)
        ctk.CTkLabel(bar, text="글자 크기", font=f(14), text_color=theme.MUTED).pack(side="right", padx=(0, 4))

        for label, v in layout.PREV_SCALES.items():
            if abs(v - self._prev_scale) < 1e-6:
                self.prev_buttons.set(label)

    def _build_history(self) -> None:
        box = tk.Frame(self, bg=theme.BG, highlightthickness=0, bd=0)
        box.pack(side="top", fill="both", expand=True)
        self.text = tk.Text(
            box, wrap="word", bg=theme.BG, fg=theme.TEXT, bd=0, highlightthickness=0,
            padx=EDGE - 4, pady=4, cursor="hand2", spacing1=0, spacing2=0, spacing3=0,
            font=(theme.FONT_LATIN, -4), insertwidth=0, takefocus=0)
        self.scrollbar = ctk.CTkScrollbar(box, command=self.text.yview, button_color=theme.BORDER_STRONG,
                                          button_hover_color=theme.MUTED, fg_color=theme.BG)
        self.text.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        self.text.tag_configure("code", font=(theme.FONT_LATIN, -CODE_PX, "bold"), foreground=theme.CODE_INK)
        self.text.tag_configure("line", lmargin1=4, lmargin2=4, rmargin=4)
        self.text.tag_configure("hover", background=theme.HOVER_BG)
        self.text.tag_configure("selected", background=theme.SELECT_BG, lmargincolor=theme.ACCENT,
                                rmargincolor=theme.ACCENT, selectbackground=theme.SELECT_BG)
        self.text.configure(state="disabled")
        self.text.bind("<Button-1>", self._on_click)
        self.text.bind("<Motion>", self._on_motion)
        self.text.bind("<Leave>", lambda _e: self._set_hover(None))
        self.text.bind("<Control-MouseWheel>", self._on_ctrl_wheel)

        self.latest_button = ctk.CTkButton(
            box, text="↓  최신 문장으로", command=self.to_latest, height=44, corner_radius=22,
            fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER, text_color="#FFFFFF", bg_color=theme.BG,
            font=ctk.CTkFont(family=theme.FONT_KO, size=15, weight="bold"))

    # ---------- App이 넘겨주는 이벤트 ----------

    def add_final(self, seq: int, ko: str) -> None:
        """확정된 문장. 한국어는 보여 주지 않고 자리만 만든다(번역이 오면 채운다)."""
        if seq in self._data:
            return
        at_bottom = self._at_bottom()
        self._data[seq] = {}
        self._items.append(seq)
        with self._editable():
            self.text.mark_set(self._mark(seq), "end-1c")
            self.text.mark_gravity(self._mark(seq), "left")
        self._prune()
        self._restyle()
        if at_bottom:
            self.text.see("end")

    def add_translation(self, seq: int, lang: str, text: str) -> None:
        if seq not in self._data:
            self.add_final(seq, "")
        at_bottom = self._at_bottom()
        self._data[seq][lang] = text
        if lang in self._langs:
            self._rewrite(seq)
        if at_bottom:
            self.text.see("end")

    def set_langs(self, langs: list[str]) -> None:
        self._langs = [lang for lang in TARGET_ORDER if lang in langs]
        at_bottom = self._at_bottom()
        with self._editable():
            self.text.delete("1.0", "end")
            for seq in self._items:
                self.text.mark_set(self._mark(seq), "end-1c")
                self.text.mark_gravity(self._mark(seq), "left")
                self._insert_block(seq, "end-1c")
        self._apply_selected_tag()
        if at_bottom:
            self.text.see("end")

    # ---------- 글자 크기, 이전 문장 크기, 📌 ----------

    @property
    def font_px(self) -> int:
        return self._size

    @property
    def count(self) -> int:
        return len(self._items)

    @property
    def selected(self) -> int | None:
        return self._selected

    def set_size(self, px: int) -> None:
        px = layout.clamp_font(px)
        if px == self._size:
            return
        at_bottom = self._at_bottom()
        self._size = px
        self._settings.display_font_px = px
        self._update_size_widgets()
        self._restyle(force=True)
        if self._selected is not None:
            self.text.see(self.text.index(self._mark(self._selected)))
        elif at_bottom:
            self.text.see("end")
        self._on_settings_changed()

    def step_size(self, delta: int) -> None:
        self.set_size(layout.step_font(self._size, delta))

    def set_prev_scale(self, scale: float) -> None:
        self._prev_scale = float(scale)
        self._settings.display_prev_scale = self._prev_scale
        self._restyle(force=True)
        self._on_settings_changed()

    def toggle_pin(self) -> None:
        self._pinned = not self._pinned
        self._settings.display_pinned = self._pinned
        self.attributes("-topmost", self._pinned)
        self._update_pin_button()
        self._on_settings_changed()

    def save_geometry(self) -> None:
        try:
            self._settings.display_geometry = self.geometry()
        except tk.TclError:
            pass

    def close(self) -> None:
        self.save_geometry()
        self._on_settings_changed()
        if self._on_close:
            self._on_close()
        self.destroy()

    # ---------- 클릭, 최신 문장으로 ----------

    def select(self, seq: int | None) -> None:
        """문장을 강조한다. 같은 문장이나 None이면 원래대로 돌아가 맨 아래로 간다."""
        if seq is None or seq == self._selected or seq not in self._data:
            self.to_latest()
            return
        self._selected = seq
        self._apply_selected_tag()
        self._restyle()
        self.latest_button.place(relx=1.0, rely=1.0, x=-24, y=-16, anchor="se")
        self.text.see(self.text.index(self._mark(seq)))
        texts = {lang: t for lang, t in self._data[seq].items() if lang in self._langs and t}
        if texts:
            threading.Thread(target=self._pipeline.speak, args=(texts,), daemon=True).start()

    def to_latest(self) -> None:
        self._selected = None
        self.latest_button.place_forget()
        self._apply_selected_tag()
        self._restyle()
        self.text.see("end")

    # ---------- 내부 ----------

    @staticmethod
    def _mark(seq: int) -> str:
        return f"m{seq}"

    def _editable(self):
        text = self.text

        class _Ctx:
            def __enter__(self_inner):
                text.configure(state="normal")

            def __exit__(self_inner, *exc):
                text.configure(state="disabled")
                return False

        return _Ctx()

    def _at_bottom(self) -> bool:
        return self.text.yview()[1] >= 0.999

    def _insert_block(self, seq: int, index: str) -> str:
        """seq 문장의 줄들을 index에 넣고, 넣은 끝 위치를 돌려준다."""
        texts = self._data.get(seq, {})
        stag = f"s{seq}"
        for lang in self._langs:
            t = texts.get(lang)
            if not t:
                continue
            tags = ("line", stag)
            self.text.insert(index, theme.LANG_CODES[lang] + " ", tags + ("code",))
            self.text.insert(index, t + "\n", tags + (f"t{seq}_{lang}",))
        return self.text.index(index)

    def _rewrite(self, seq: int) -> None:
        pos = self._items.index(seq)
        later = self._items[pos + 1:]
        with self._editable():
            start = self.text.index(self._mark(seq))
            end = self.text.index(self._mark(later[0])) if later else self.text.index("end-1c")
            self.text.delete(start, end)
            # 뒤 문장 표시 중 지금 위치에 겹친 것(빈 문장)은 새로 넣은 글 뒤로 옮긴다
            stuck = [s for s in later if self.text.index(self._mark(s)) == start]
            self.text.mark_set("ins", start)
            self.text.mark_gravity("ins", "right")
            for s in stuck:
                self.text.mark_gravity(self._mark(s), "right")
            self._insert_block(seq, "ins")
            for s in stuck:
                self.text.mark_gravity(self._mark(s), "left")
            self.text.mark_set(self._mark(seq), start)
            self.text.mark_unset("ins")
        self._apply_selected_tag()

    def _prune(self) -> None:
        while len(self._items) > MAX_ITEMS:
            old = self._items.pop(0)
            with self._editable():
                end = self.text.index(self._mark(self._items[0])) if self._items else "end-1c"
                self.text.delete("1.0", end)
                self.text.mark_unset(self._mark(old))
            self.text.tag_delete(f"s{old}", *[f"t{old}_{lang}" for lang in TARGET_ORDER])
            self._data.pop(old, None)
            self._style_cache.pop(old, None)
            if self._selected == old:
                self._selected = None
                self.latest_button.place_forget()
            if self._hover == old:
                self._hover = None

    def _restyle(self, force: bool = False) -> None:
        sel = self._items.index(self._selected) if self._selected in self._data else None
        sizes = layout.display_sizes(len(self._items), self._size, self._prev_scale, sel)
        for seq, style in zip(self._items, sizes):
            if not force and self._style_cache.get(seq) == style:
                continue
            self._style_cache[seq] = style
            px, weight, color = style
            for lang in TARGET_ORDER:
                self.text.tag_configure(f"t{seq}_{lang}", font=(theme.family_for(lang), -px, weight),
                                        foreground=color)
        self.text.tag_raise("hover")
        self.text.tag_raise("selected")

    def _apply_selected_tag(self) -> None:
        self.text.tag_remove("selected", "1.0", "end")
        if self._selected is not None:
            for start, end in _pairs(self.text.tag_ranges(f"s{self._selected}")):
                self.text.tag_add("selected", start, end)
        self._set_hover(self._hover, force=True)

    def _seq_at(self, event) -> int | None:
        index = self.text.index(f"@{event.x},{event.y}")
        for tag in self.text.tag_names(index):
            if tag.startswith("s") and tag[1:].lstrip("-").isdigit():
                return int(tag[1:])
        return None

    def _on_click(self, event) -> str:
        seq = self._seq_at(event)
        if seq is not None:
            self.select(seq)
        return "break"

    def _on_motion(self, event) -> None:
        self._set_hover(self._seq_at(event))

    def _set_hover(self, seq: int | None, force: bool = False) -> None:
        if seq == self._hover and not force:
            return
        self._hover = seq
        self.text.tag_remove("hover", "1.0", "end")
        if seq is not None and seq != self._selected:
            for start, end in _pairs(self.text.tag_ranges(f"s{seq}")):
                self.text.tag_add("hover", start, end)

    def _on_ctrl_wheel(self, event) -> str:
        if event.delta:
            self.step_size(1 if event.delta > 0 else -1)
        return "break"

    def _on_slide(self, value: float) -> None:
        self.set_size(int(round(value)))

    def _on_prev_scale(self, label: str) -> None:
        self.set_prev_scale(layout.PREV_SCALES[label])

    def _update_size_widgets(self) -> None:
        self.slider.set(self._size)
        self.size_label.configure(text=f"{self._size}px")

    def _update_pin_button(self) -> None:
        if self._pinned:
            self.pin_button.configure(fg_color=theme.ACCENT_SOFT, border_color=theme.ACCENT,
                                      text_color=theme.ACCENT_INK)
        else:
            self.pin_button.configure(fg_color=theme.BG, border_color=theme.BORDER_STRONG,
                                      text_color=theme.OFF_INK)


def _pairs(ranges):
    it = iter(ranges)
    return list(zip(it, it))
