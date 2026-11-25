from sukpago.languages import TARGET_ORDER
from sukpago.ui.layout import FONT_MAX, FONT_MIN, clamp_font, ordered_texts, step_font


def test_clamp_font():
    assert clamp_font(10) == FONT_MIN == 24
    assert clamp_font(500) == FONT_MAX == 120
    assert clamp_font(52) == 52


def test_step_font():
    assert step_font(52, 1) == 60
    assert step_font(52, -1) == 44
    assert step_font(120, 1) == 120
    assert step_font(24, -1) == 24


def test_ordered_texts_uses_enabled_langs_in_fixed_order():
    texts = {"en": "E", "zh": "Z", "mn": "M"}
    assert ordered_texts(texts, ["zh", "mn"], TARGET_ORDER) == [("mn", "M"), ("zh", "Z")]


def test_ordered_texts_skips_missing_translations():
    assert ordered_texts({"mn": "M"}, ["mn", "zh"], TARGET_ORDER) == [("mn", "M")]
    assert ordered_texts({}, ["mn"], TARGET_ORDER) == []
