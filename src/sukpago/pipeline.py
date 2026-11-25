"""마이크 → 인식 → 문장 정리 → 번역 → 음성. 각 단계는 자기 스레드에서 돌고 결과는 events 큐로 UI에 보낸다."""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from .asr.base import Recognizer
from .languages import TARGET_ORDER
from .text.assembler import SentenceAssembler
from .text.glossary import Glossary

if TYPE_CHECKING:
    from .asr.mic import Mic
    from .audio import Player
    from .config import Settings
    from .phrases import Phrase
    from .tts.base import Speaker

TICK_S = 0.1
DELAY_AT = 3
_STOP = object()


@dataclass(frozen=True)
class Partial:
    text: str


@dataclass(frozen=True)
class Final:
    seq: int
    ko: str
    source: str  # "live" | "text"


@dataclass(frozen=True)
class Translation:
    seq: int
    lang: str
    text: str
    engine: str
    fell_back: bool
    reason: str | None


@dataclass(frozen=True)
class Status:
    kind: str  # "mic_error" | "fallback" | "quota" | "tts_error" | "audio_error" | "delay" | "info"
    message: str


def _default_audio_path(phrase: Phrase, lang: str) -> Path:
    from .phrases import audio_path

    return audio_path(phrase, lang)


class Pipeline:
    def __init__(self, *, recognizer_factory: Callable[[], Recognizer], router: Any,
                 speaker: Speaker, player: Player,
                 mic_factory: Callable[[str | None, Callable[[np.ndarray], None]], Mic],
                 settings: Settings, glossary: Glossary,
                 clock: Callable[[], float] = time.monotonic,
                 audio_path: Callable[[Phrase, str], Path] | None = None) -> None:
        self._recognizer_factory = recognizer_factory
        self._router = router
        self._speaker = speaker
        self._player = player
        self._mic_factory = mic_factory
        self._settings = settings
        self._glossary = glossary
        self._clock = clock
        self._audio_path = audio_path or _default_audio_path

        self.events: queue.Queue = queue.Queue()
        self._lock = threading.Lock()
        self._seq = 0
        self._quota_told = False
        self._delayed = False
        self._closed = False

        self._mic: Mic | None = None
        self._audio_q: queue.Queue | None = None
        self._asr_thread: threading.Thread | None = None
        self._assembler: SentenceAssembler | None = None

        self._trans_q: queue.Queue = queue.Queue()
        self._speech_q: queue.Queue = queue.Queue()
        self._trans_thread = threading.Thread(target=self._translate_loop, name="pipeline-translate",
                                              daemon=True)
        self._speech_thread = threading.Thread(target=self._speech_loop, name="pipeline-speech",
                                               daemon=True)
        self._trans_thread.start()
        self._speech_thread.start()

    # ---- 설정 ----

    def _langs(self) -> list[str]:
        with self._lock:
            on = set(self._settings.langs)
        return [lang for lang in TARGET_ORDER if lang in on]

    def _online(self) -> bool:
        with self._lock:
            return bool(self._settings.online)

    def set_langs(self, langs: list[str]) -> None:
        with self._lock:
            self._settings.langs = [lang for lang in TARGET_ORDER if lang in set(langs)]

    def set_online(self, online: bool) -> None:
        with self._lock:
            self._settings.online = bool(online)

    def set_glossary(self, g: Glossary) -> None:
        with self._lock:
            self._glossary = g
            if self._assembler is not None:
                self._assembler.glossary = g

    # ---- 실시간 ----

    @property
    def live(self) -> bool:
        return self._asr_thread is not None and self._asr_thread.is_alive()

    def start_live(self) -> None:
        if self.live or self._closed:
            return
        try:
            recognizer = self._recognizer_factory()
        except Exception as e:
            self._emit(Status("mic_error", f"음성 인식을 시작하지 못했습니다: {e}"))
            return
        audio_q: queue.Queue = queue.Queue()
        try:
            mic = self._mic_factory(None, audio_q.put)
            mic.start()
        except Exception as e:
            self._emit(Status("mic_error", f"마이크를 열지 못했습니다: {e}"))
            return
        with self._lock:
            self._assembler = SentenceAssembler(self._glossary)
        self._mic, self._audio_q = mic, audio_q
        self._asr_thread = threading.Thread(target=self._asr_loop, args=(recognizer, audio_q),
                                            name="pipeline-asr", daemon=True)
        self._asr_thread.start()

    def stop_live(self, timeout: float = 5.0) -> None:
        mic, audio_q, thread = self._mic, self._audio_q, self._asr_thread
        self._mic = self._audio_q = None
        if mic is not None:
            try:
                mic.stop()
            except Exception:
                pass
        if audio_q is not None:
            audio_q.put(_STOP)
        if thread is not None:
            thread.join(timeout)
        self._asr_thread = None

    def _asr_loop(self, recognizer: Recognizer, audio_q: queue.Queue) -> None:
        assembler = self._assembler
        assert assembler is not None
        last_partial = ""
        last_tick = self._clock()

        def handle(events) -> None:
            nonlocal last_partial
            for ev in events:
                if ev.kind == "partial":
                    if ev.text and ev.text != last_partial:
                        last_partial = ev.text
                        self._emit(Partial(ev.text))
                elif ev.kind == "final":
                    last_partial = ""
                    self._finals(assembler.feed(ev.text, self._clock()), "live")

        while not self._closed:
            try:
                item = audio_q.get(timeout=TICK_S)
            except queue.Empty:
                item = None
            if item is _STOP:
                break
            if item is not None:
                handle(recognizer.accept(item))
            now = self._clock()
            if item is None or now - last_tick >= TICK_S:
                last_tick = now
                self._finals(assembler.tick(now), "live")
        if self._closed:
            return
        # 멈춤: 남은 오디오와 조각까지 확정한다.
        while True:
            try:
                item = audio_q.get_nowait()
            except queue.Empty:
                break
            if item is not _STOP:
                handle(recognizer.accept(item))
        handle(recognizer.finish())
        self._finals(assembler.flush(), "live")

    # ---- 직접 입력과 번역 ----

    def _finals(self, sentences: list[str], source: str) -> None:
        for s in sentences:
            self._final(s, source)

    def _final(self, ko: str, source: str) -> int:
        with self._lock:
            self._seq += 1
            seq = self._seq
        self._emit(Final(seq, ko, source))
        self._trans_q.put((seq, ko, source))
        if self._trans_q.qsize() >= DELAY_AT and not self._delayed:
            self._delayed = True
            self._emit(Status("delay", "번역 지연"))
        return seq

    def _translate_loop(self) -> None:
        while not self._closed:
            item = self._trans_q.get()
            if item is _STOP or self._closed:
                return
            seq, ko, source = item
            online = self._online()
            fallback_reason: str | None = None
            for lang in self._langs():
                try:
                    r = self._router.translate(ko, lang, online=online)
                except Exception as e:
                    self._emit(Status("info", f"번역하지 못했습니다({lang}): {e}"))
                    continue
                reason = getattr(r, "reason", None)
                self._emit(Translation(seq, lang, r.text, r.engine, r.fell_back, reason))
                if reason == "quota":
                    if not self._quota_told:
                        self._quota_told = True
                        self._emit(Status("quota", "오늘 번역 한도 초과"))
                elif r.fell_back and fallback_reason is None:
                    fallback_reason = reason or "error"
            if fallback_reason is not None:
                self._emit(Status("fallback", f"오프라인으로 전환됨 ({fallback_reason})"))
            if self._trans_q.empty():
                self._delayed = False

    # ---- 음성 ----

    def play_phrase(self, phrase: Phrase) -> None:
        self._speech_q.put(lambda: self._play_phrase_now(phrase))

    def _speech_loop(self) -> None:
        while not self._closed:
            job = self._speech_q.get()
            if job is _STOP or self._closed:
                return
            try:
                job()
            except Exception as e:
                self._emit(Status("info", f"음성 처리 오류: {e}"))

    def _synth(self, text: str, lang: str) -> bytes | None:
        try:
            return self._speaker.synth(text, lang)
        except Exception as e:
            self._emit(Status("tts_error", f"음성을 만들지 못했습니다: {e}"))
            return None

    def _play(self, fn: Callable[[], None]) -> None:
        try:
            fn()
        except Exception as e:
            self._emit(Status("audio_error", f"소리를 재생하지 못했습니다: {e}"))

    def _play_phrase_now(self, phrase: Phrase) -> None:
        online = self._online()
        items: list[Path | bytes] = []
        for lang in self._langs():
            path = Path(self._audio_path(phrase, lang))
            if path.is_file():
                items.append(path)
            elif online and phrase.texts.get(lang):
                clip = self._synth(phrase.texts[lang], lang)
                if clip is not None:
                    items.append(clip)
        if not items:
            return
        if all(isinstance(i, Path) for i in items):
            self._play(lambda: self._player.play_files(items))
            return
        clips: list[bytes] = []
        for i in items:
            if isinstance(i, Path):
                try:
                    clips.append(i.read_bytes())
                except OSError as e:
                    self._emit(Status("audio_error", f"음성 파일을 읽지 못했습니다: {e}"))
            else:
                clips.append(i)
        if clips:
            self._play(lambda: self._player.play(clips))

    # ---- 공통 ----

    def _emit(self, ev: object) -> None:
        self.events.put(ev)

    def shutdown(self) -> None:
        if self._closed:
            return
        self.stop_live(timeout=0.5)
        self._closed = True
        self._trans_q.put(_STOP)
        self._speech_q.put(_STOP)
        try:
            self._player.stop()
        except Exception:
            pass
        for t in (self._trans_thread, self._speech_thread):
            t.join(0.5)
