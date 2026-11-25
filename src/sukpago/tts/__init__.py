"""문장을 음성(mp3 바이트)으로 바꾸는 부분."""

from sukpago.tts.base import Speaker, TtsError
from sukpago.tts.cache import CachedSpeaker
from sukpago.tts.edge import EdgeSpeaker

__all__ = ["CachedSpeaker", "EdgeSpeaker", "Speaker", "TtsError"]
