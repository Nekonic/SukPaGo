"""(문장, 언어)별 합성 결과 LRU 캐시."""

from __future__ import annotations

import threading
from collections import OrderedDict

from sukpago.tts.base import Speaker


class CachedSpeaker:
    def __init__(self, inner: Speaker, max_items: int = 200):
        self.inner = inner
        self.name = inner.name
        self.max_items = max_items
        self._items: OrderedDict[tuple[str, str], bytes] = OrderedDict()
        self._lock = threading.Lock()

    def synth(self, text: str, lang: str) -> bytes:
        key = (text, lang)
        with self._lock:
            if key in self._items:
                self._items.move_to_end(key)
                return self._items[key]
        audio = self.inner.synth(text, lang)   # 실패(TtsError)는 저장하지 않는다
        with self._lock:
            self._items[key] = audio
            self._items.move_to_end(key)
            while len(self._items) > self.max_items:
                self._items.popitem(last=False)
        return audio
