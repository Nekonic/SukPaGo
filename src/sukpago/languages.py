"""번역 대상 언어와 엔진별 언어 코드."""

from __future__ import annotations

from dataclasses import dataclass

SOURCE_MYMEMORY = "ko"
SOURCE_NLLB = "kor_Hang"


@dataclass(frozen=True)
class Language:
    id: str
    name_ko: str
    mymemory: str
    nllb: str
    hymt_name: str
    edge_voice: str


LANGUAGES: dict[str, Language] = {
    "mn": Language("mn", "몽골어", "mn", "khk_Cyrl",
                   "Mongolian (Cyrillic script, as used in Mongolia)", "mn-MN-YesuiNeural"),
    "zh": Language("zh", "중국어", "zh-CN", "zho_Hans", "中文", "zh-CN-XiaoxiaoNeural"),
    "en": Language("en", "영어", "en", "eng_Latn", "English", "en-US-JennyNeural"),
}

TARGET_ORDER: tuple[str, ...] = ("mn", "zh", "en")


def get(lang_id: str) -> Language:
    try:
        return LANGUAGES[lang_id]
    except KeyError:
        raise KeyError(f"지원하지 않는 언어: {lang_id!r}") from None
