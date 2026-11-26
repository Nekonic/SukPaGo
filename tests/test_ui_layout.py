from sukpago.languages import TARGET_ORDER
from sukpago.ui.layout import FONT_MAX, FONT_MIN, clamp_font, level_fraction, ordered_texts, step_font


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


def test_level_fraction():
    assert level_fraction(-120) == 0.0
    assert level_fraction(-60) == 0.0
    assert level_fraction(-30) == 0.5
    assert level_fraction(3) == 1.0


def test_wrap_width_divides_out_widget_scaling():
    from sukpago.ui.layout import wrap_width
    assert wrap_width(1000, 1.0) == 992
    assert wrap_width(1250, 1.25) == 993
    assert wrap_width(100, 1.0) == 200
