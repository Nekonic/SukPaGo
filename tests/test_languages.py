import pytest

from sukpago import languages as L


def test_target_order_is_mn_zh_en():
    assert L.TARGET_ORDER == ("mn", "zh", "en")
    assert set(L.TARGET_ORDER) == set(L.LANGUAGES)


def test_engine_codes():
    assert (L.get("mn").mymemory, L.get("mn").nllb) == ("mn", "khk_Cyrl")
    assert (L.get("zh").mymemory, L.get("zh").nllb) == ("zh-CN", "zho_Hans")
    assert (L.get("en").mymemory, L.get("en").nllb) == ("en", "eng_Latn")
    assert (L.SOURCE_MYMEMORY, L.SOURCE_NLLB) == ("ko", "kor_Hang")


def test_hymt_names():
    assert "Cyrillic" in L.get("mn").hymt_name
    assert L.get("zh").hymt_name == "中文"
    assert L.get("en").hymt_name == "English"


def test_unknown_language_raises():
    with pytest.raises(KeyError, match="지원하지 않는 언어"):
        L.get("ja")
