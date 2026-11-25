"""메인 창의 패널 3개: 용어 고치기, 내 문장 추가, 마이크 상태."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any, Callable

import customtkinter as ctk

from . import layout, theme

if TYPE_CHECKING:
    from ..text.glossary import Glossary

Post = Callable[[Callable[[], None]], None]   # 작업 스레드에서 Tk 스레드로 일을 넘기는 함수

DEFAULT_MIC = "기본 마이크"


def _font(size: int = 14, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(family=theme.FONT_KO, size=size, weight=weight)


class Card(ctk.CTkFrame):
    """회색 카드: 제목과 설명이 있는 패널 틀."""

    def __init__(self, master, title: str, hint: str | None = None) -> None:
        super().__init__(master, fg_color=theme.CARD, border_color=theme.BORDER, border_width=1,
                         corner_radius=14)
        self.columnconfigure(0, weight=1)
        self.title_label = ctk.CTkLabel(self, text=title, font=_font(16, "bold"), text_color=theme.INK,
                                        anchor="w")
        self.title_label.grid(row=0, column=0, sticky="ew", padx=14, pady=(8, 0))
        self.hint_label = None
        if hint:
            self.hint_label = ctk.CTkLabel(self, text=hint, font=_font(13), text_color=theme.MUTED,
                                           anchor="w", justify="left", wraplength=300)
            self.hint_label.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 4))
            self.bind("<Configure>", self._rewrap, add="+")

    def _rewrap(self, event) -> None:
        if self.hint_label is not None:
            self.hint_label.configure(wraplength=max(120, event.width - 40))


class Segmented(ctk.CTkFrame):
    """하나만 고르는 버튼 묶음. 고른 버튼은 색 배경에 흰 글자, 나머지는 흰 배경에 회색 글자."""

    def __init__(self, master, values: list[str], command: Callable[[str], None] | None = None, *,
                 height: int = 36, size: int = 15, colors: dict[str, str] | None = None) -> None:
        super().__init__(master, fg_color=theme.BG, border_color=theme.BORDER_STRONG, border_width=1,
                         corner_radius=10)
        self._command = command
        self._colors = colors or {}
        self._value: str | None = None
        self.buttons: dict[str, ctk.CTkButton] = {}
        for i, v in enumerate(values):
            b = ctk.CTkButton(self, text=v, height=height, width=20, corner_radius=8, border_width=0,
                              font=_font(size, "bold"), command=lambda x=v: self._click(x))
            b.grid(row=0, column=i, padx=(4 if i == 0 else 0, 4), pady=4)
            self.buttons[v] = b
        self._paint()

    def _click(self, value: str) -> None:
        if value == self._value:
            return
        self.set(value)
        if self._command:
            self._command(value)

    def get(self) -> str | None:
        return self._value

    def set(self, value: str) -> None:
        self._value = value
        self._paint()

    def _paint(self) -> None:
        for v, b in self.buttons.items():
            if v == self._value:
                c = self._colors.get(v, theme.ACCENT)
                b.configure(fg_color=c, hover_color=c, text_color="#FFFFFF")
            else:
                b.configure(fg_color=theme.BG, hover_color=theme.HOVER_BG, text_color=theme.OFF_INK)


def entry(master, placeholder: str, height: int = 36, size: int = 15) -> ctk.CTkEntry:
    return ctk.CTkEntry(master, placeholder_text=placeholder, height=height, corner_radius=8,
                        border_width=1, border_color=theme.INPUT_BORDER, fg_color=theme.BG,
                        text_color=theme.INK, placeholder_text_color=theme.MUTED, font=_font(size))


def primary_button(master, text: str, command, height: int = 36, size: int = 14, width: int = 64):
    return ctk.CTkButton(master, text=text, command=command, height=height, width=width, corner_radius=8,
                         fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER, text_color="#FFFFFF",
                         font=_font(size, "bold"))


def small_x_button(master, command):
    return ctk.CTkButton(master, text="✕", command=command, width=28, height=28, corner_radius=6,
                         fg_color=theme.BG, hover_color=theme.HOVER_BG, text_color=theme.OFF_INK,
                         border_width=1, border_color=theme.BORDER_STRONG, font=_font(12, "bold"))


def list_row(master) -> ctk.CTkFrame:
    row = ctk.CTkFrame(master, fg_color=theme.BG, border_color=theme.DIVIDER, border_width=1, corner_radius=8)
    return row


def field_label(master, text: str) -> ctk.CTkLabel:
    return ctk.CTkLabel(master, text=text, font=_font(12), text_color=theme.MUTED, anchor="w", height=16)


class GlossaryPanel(Card):
    """용어 고치기: 인식된 말 → 바꿀 말. 바꾸면 저장하고 파이프라인에 알린다."""

    def __init__(self, master, glossary: "Glossary", *, config_api: Any, pipeline: Any,
                 notify: Callable[[str, str], None] | None = None) -> None:
        super().__init__(master, "용어 고치기", "잘못 알아들은 말을 등록하면 다음부터 자동으로 고쳐서 번역합니다.")
        self.glossary = glossary
        self._config = config_api
        self._pipeline = pipeline
        self._notify = notify or (lambda kind, msg: None)

        form = ctk.CTkFrame(self, fg_color="transparent")
        form.grid(row=2, column=0, sticky="ew", padx=14)
        form.columnconfigure((0, 1), weight=1, uniform="g")
        field_label(form, "인식된 말").grid(row=0, column=0, sticky="w")
        field_label(form, "바꿀 말").grid(row=0, column=1, sticky="w", padx=(8, 0))
        self.wrong_entry = entry(form, "노트북 에램")
        self.wrong_entry.grid(row=1, column=0, sticky="ew")
        self.right_entry = entry(form, "NotebookLM")
        self.right_entry.grid(row=1, column=1, sticky="ew", padx=(8, 0))
        primary_button(form, "추가", self.add).grid(row=1, column=2, padx=(8, 0))
        self.right_entry.bind("<Return>", lambda _e: self.add())

        self.list_frame = ctk.CTkScrollableFrame(self, fg_color="transparent", height=48)
        self.list_frame.grid(row=3, column=0, sticky="nsew", padx=8, pady=(4, 8))
        self.list_frame.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)
        self.refresh()

    def add(self) -> None:
        wrong, right = self.wrong_entry.get().strip(), self.right_entry.get().strip()
        if not wrong or not right:
            self._notify("info", "인식된 말과 바꿀 말을 모두 입력하세요.")
            return
        self.glossary.add(wrong, right)
        self.wrong_entry.delete(0, "end")
        self.right_entry.delete(0, "end")
        self._changed()

    def remove(self, wrong: str) -> None:
        self.glossary.remove(wrong)
        self._changed()

    def _changed(self) -> None:
        self._config.save_glossary(self.glossary)
        self._pipeline.set_glossary(self.glossary)
        self.refresh()

    def refresh(self) -> None:
        for w in self.list_frame.winfo_children():
            w.destroy()
        for i, rule in enumerate(self.glossary.rules):
            row = list_row(self.list_frame)
            row.grid(row=i, column=0, sticky="ew", pady=(0, 6), padx=(0, 4))
            row.columnconfigure(2, weight=1)
            ctk.CTkLabel(row, text=rule.wrong, font=_font(14, "normal"), text_color=theme.MUTED).grid(
                row=0, column=0, padx=(10, 6), pady=4)
            ctk.CTkLabel(row, text="→", font=_font(14, "bold"), text_color=theme.ACCENT).grid(row=0, column=1)
            ctk.CTkLabel(row, text=rule.right, font=_font(14, "bold"), text_color=theme.INK, anchor="w").grid(
                row=0, column=2, sticky="ew", padx=6)
            small_x_button(row, lambda w=rule.wrong: self.remove(w)).grid(row=0, column=3, padx=4, pady=4)


class CustomPhrasePanel(Card):
    """내 문장 추가: 번역(translate_once)과 음성(synth)을 작업 스레드에서 한 번만 만들어 저장한다."""

    def __init__(self, master, *, pipeline: Any, phrases_api: Any, settings: Any, post: Post,
                 speaker: Any | None = None, on_change: Callable[[], None] | None = None,
                 notify: Callable[[str, str], None] | None = None) -> None:
        super().__init__(master, "내 문장 추가",
                         "자주 하는 말을 등록하면 아래 빠른 안내 버튼에 생깁니다. 번역은 추가할 때 한 번만 해서 저장합니다.")
        self._pipeline = pipeline
        self._phrases = phrases_api
        self._settings = settings
        self._post = post
        self._speaker = speaker
        self._on_change = on_change or (lambda: None)
        self._notify = notify or (lambda kind, msg: None)
        self.busy = False

        form = ctk.CTkFrame(self, fg_color="transparent")
        form.grid(row=2, column=0, sticky="ew", padx=14)
        form.columnconfigure(0, weight=1)
        field_label(form, "문장").grid(row=0, column=0, sticky="w")
        self.text_entry = entry(form, "휴대폰 넣어 주세요.")
        self.text_entry.grid(row=1, column=0, sticky="ew")
        self.text_entry.bind("<Return>", lambda _e: self.add())
        self.add_button = primary_button(form, "추가", self.add)
        self.add_button.grid(row=1, column=1, padx=(8, 0))

        self.list_frame = ctk.CTkScrollableFrame(self, fg_color="transparent", height=48)
        self.list_frame.grid(row=3, column=0, sticky="nsew", padx=8, pady=(4, 8))
        self.list_frame.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)
        self.refresh()

    def customs(self) -> list[Any]:
        try:
            return [p for p in self._phrases.load_all() if p.custom]
        except Exception:
            return []

    def add(self) -> None:
        if self.busy:
            return
        ko = self.text_entry.get().strip()
        problem = layout.check_direct_input(ko)
        if problem:
            self._notify("info", problem)
            return
        self.busy = True
        self.add_button.configure(state="disabled", text="번역 중…")
        online = bool(getattr(self._settings, "online", True))
        threading.Thread(target=self._work, args=(ko, online), daemon=True).start()

    def _work(self, ko: str, online: bool) -> None:
        """작업 스레드: 번역 → 저장 → (온라인이면) 언어별 mp3."""
        try:
            texts = self._pipeline.translate_once(ko)
            phrase = self._phrases.add_custom(ko, texts)
        except Exception as e:  # 번역·저장 실패는 알리고 끝낸다
            self._post(lambda e=e: self._done(False, f"내 문장을 추가하지 못했습니다: {e}"))
            return
        tts_failed = False
        if online and self._speaker is not None:
            for lang, text in texts.items():
                try:
                    data = self._speaker.synth(text, lang)
                    path = self._phrases.audio_path(phrase, lang)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(data)
                except Exception:
                    tts_failed = True
        msg = "내 문장을 추가했습니다." + (" (음성은 만들지 못했습니다)" if tts_failed else "")
        self._post(lambda: self._done(True, msg))

    def _done(self, ok: bool, msg: str) -> None:
        self.busy = False
        self.add_button.configure(state="normal", text="추가")
        if ok:
            self.text_entry.delete(0, "end")
            self.refresh()
            self._on_change()
        self._notify("info" if ok else "tts_error", msg)

    def remove(self, key: str) -> None:
        try:
            self._phrases.remove_custom(key)
        except Exception as e:
            self._notify("info", f"지우지 못했습니다: {e}")
        self.refresh()
        self._on_change()

    def refresh(self) -> None:
        for w in self.list_frame.winfo_children():
            w.destroy()
        for i, p in enumerate(self.customs()):
            row = list_row(self.list_frame)
            row.grid(row=i, column=0, sticky="ew", pady=(0, 6), padx=(0, 4))
            row.columnconfigure(0, weight=1)
            ctk.CTkLabel(row, text=p.ko, font=_font(14), text_color=theme.INK, anchor="w").grid(
                row=0, column=0, sticky="ew", padx=(10, 6), pady=4)
            ctk.CTkLabel(row, text="번역 저장됨", font=_font(12), text_color=theme.GREEN).grid(row=0, column=1)
            small_x_button(row, lambda k=p.key: self.remove(k)).grid(row=0, column=2, padx=4, pady=4)


class MicPanel(Card):
    """마이크 상태: 장치 선택, 소리 크기 막대, 상태 문구."""

    def __init__(self, master, *, mic_api: Any | None, settings: Any,
                 on_device: Callable[[str | None], None] | None = None) -> None:
        super().__init__(master, "마이크 상태")
        self._mic = mic_api
        self._settings = settings
        self._on_device = on_device or (lambda d: None)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=2, column=0, sticky="nsew", padx=14, pady=(0, 10))
        body.columnconfigure(0, weight=1)
        field_label(body, "마이크").grid(row=0, column=0, sticky="w")
        self.device_menu = ctk.CTkOptionMenu(
            body, values=[DEFAULT_MIC], command=self._select, height=36, corner_radius=8,
            fg_color=theme.BG, button_color=theme.BORDER_STRONG, button_hover_color=theme.INPUT_BORDER,
            text_color=theme.INK, font=_font(14), dropdown_font=_font(14), dynamic_resizing=False)
        self.device_menu.grid(row=1, column=0, sticky="ew")
        ctk.CTkButton(body, text="↻", width=36, height=36, corner_radius=8, command=self.refresh_devices,
                      fg_color=theme.BG, hover_color=theme.HOVER_BG, text_color=theme.INK, border_width=1,
                      border_color=theme.BORDER_STRONG, font=_font(16, "bold")).grid(row=1, column=1, padx=(6, 0))
        field_label(body, "입력 소리 크기").grid(row=2, column=0, sticky="w", pady=(6, 2))
        self.level_bar = ctk.CTkProgressBar(body, height=12, corner_radius=6, fg_color=theme.DIVIDER,
                                            progress_color=theme.GREEN)
        self.level_bar.grid(row=3, column=0, columnspan=2, sticky="ew")
        self.level_bar.set(0)
        self.state_label = ctk.CTkLabel(body, text="마이크를 켜면 소리 크기가 보입니다.", font=_font(14, "bold"),
                                        text_color=theme.MUTED, anchor="w", justify="left", wraplength=260)
        self.state_label.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self.refresh_devices()

    def refresh_devices(self) -> None:
        devices: list[str] = []
        if self._mic is not None:
            try:
                devices = list(self._mic.list_devices())
            except Exception:
                devices = []
        self.device_menu.configure(values=[DEFAULT_MIC] + devices)
        current = getattr(self._settings, "mic_device", None)
        self.device_menu.set(current if current in devices else DEFAULT_MIC)

    def _select(self, choice: str) -> None:
        device = None if choice == DEFAULT_MIC else choice
        self._settings.mic_device = device
        self._on_device(device)

    def update_level(self, dbfs: float, clip_ratio: float, state: str) -> None:
        color = theme.mic_color(state)
        self.level_bar.set(layout.mic_bar_fraction(dbfs))
        self.level_bar.configure(progress_color=color)
        self.state_label.configure(text=theme.MIC_TEXT.get(state, state), text_color=color)

    def reset_level(self) -> None:
        self.level_bar.set(0)
        self.state_label.configure(text="마이크를 켜면 소리 크기가 보입니다.", text_color=theme.MUTED)
