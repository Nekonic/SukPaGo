import asyncio

import pytest

from sukpago.tts.base import TtsError
from sukpago.tts.cache import CachedSpeaker
from sukpago.tts.edge import EdgeSpeaker


class FakeCommunicate:
    """edge_tts.Communicate와 같은 모양의 가짜. 부를 때마다 calls에 (text, voice)를 남긴다."""

    def __init__(self, chunks, *, delay=0.0, error=None):
        self.chunks = chunks
        self.delay = delay
        self.error = error
        self.calls = []

    def __call__(self, text, voice):
        self.calls.append((text, voice))
        return self

    async def stream(self):
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        for c in self.chunks:
            yield c


def test_edge_joins_audio_chunks_and_skips_other_types():
    comm = FakeCommunicate([
        {"type": "audio", "data": b"ab"},
        {"type": "WordBoundary", "offset": 0},
        {"type": "audio", "data": b"cd"},
    ])
    sp = EdgeSpeaker(communicate=comm)
    assert sp.name == "edge-tts"
    assert sp.synth("hello", "en") == b"abcd"


def test_edge_uses_language_voice_and_sends_mongolian_as_is():
    comm = FakeCommunicate([{"type": "audio", "data": b"x"}])
    sp = EdgeSpeaker(communicate=comm)
    sp.synth("Анхаарлаа төвлөрүүл.", "mn")
    sp.synth("请注意。", "zh")
    sp.synth("Attention.", "en")
    assert comm.calls == [
        ("Анхаарлаа төвлөрүүл.", "mn-MN-YesuiNeural"),
        ("请注意。", "zh-CN-XiaoxiaoNeural"),
        ("Attention.", "en-US-JennyNeural"),
    ]


def test_edge_empty_audio_is_error():
    sp = EdgeSpeaker(communicate=FakeCommunicate([{"type": "WordBoundary"}]))
    with pytest.raises(TtsError):
        sp.synth("hello", "en")


def test_edge_exception_becomes_tts_error():
    sp = EdgeSpeaker(communicate=FakeCommunicate([], error=OSError("network down")))
    with pytest.raises(TtsError):
        sp.synth("hello", "en")


def test_edge_constructor_exception_becomes_tts_error():
    def boom(text, voice):
        raise ValueError("bad voice")

    with pytest.raises(TtsError):
        EdgeSpeaker(communicate=boom).synth("hello", "en")


def test_edge_timeout_becomes_tts_error():
    comm = FakeCommunicate([{"type": "audio", "data": b"x"}], delay=1.0)
    sp = EdgeSpeaker(timeout=0.05, communicate=comm)
    with pytest.raises(TtsError):
        sp.synth("hello", "en")


def test_edge_unknown_language_is_error():
    sp = EdgeSpeaker(communicate=FakeCommunicate([{"type": "audio", "data": b"x"}]))
    with pytest.raises(TtsError):
        sp.synth("hello", "fr")


class CountingSpeaker:
    name = "fake"

    def __init__(self):
        self.calls = []

    def synth(self, text, lang):
        self.calls.append((text, lang))
        return f"{text}/{lang}".encode()


def test_cache_calls_inner_once_per_text_and_lang():
    inner = CountingSpeaker()
    sp = CachedSpeaker(inner)
    assert sp.name == "fake"
    assert sp.synth("a", "mn") == b"a/mn"
    assert sp.synth("a", "mn") == b"a/mn"
    assert sp.synth("a", "zh") == b"a/zh"
    assert inner.calls == [("a", "mn"), ("a", "zh")]


def test_cache_evicts_least_recently_used():
    inner = CountingSpeaker()
    sp = CachedSpeaker(inner, max_items=200)
    for i in range(200):
        sp.synth(str(i), "en")
    sp.synth("0", "en")            # 0을 최근으로 올림 -> 가장 오래 안 쓴 것은 1
    sp.synth("200", "en")          # 201번째
    n = len(inner.calls)
    sp.synth("0", "en")
    assert len(inner.calls) == n   # 0은 남아 있음
    sp.synth("1", "en")
    assert len(inner.calls) == n + 1   # 1은 버려졌음


def test_cache_does_not_store_errors():
    class Flaky:
        name = "flaky"

        def __init__(self):
            self.n = 0

        def synth(self, text, lang):
            self.n += 1
            if self.n == 1:
                raise TtsError("first fails")
            return b"ok"

    sp = CachedSpeaker(Flaky())
    with pytest.raises(TtsError):
        sp.synth("a", "en")
    assert sp.synth("a", "en") == b"ok"
