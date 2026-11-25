from sukpago.ui import layout
from sukpago.ui.theme import MUTED, TEXT

RECENT = "#2A303A"


def test_display_sizes_latest_recent_older():
    out = layout.display_sizes(6, 52, 0.75, None)
    assert len(out) == 6
    assert out[-1] == (52, "bold", TEXT)
    for item in out[2:5]:
        assert item == (39, "bold", RECENT)
    for item in out[:2]:
        assert item == (31, "normal", MUTED)


def test_display_sizes_empty_and_single():
    assert layout.display_sizes(0, 52, 0.75, None) == []
    assert layout.display_sizes(1, 52, 0.75, None) == [(52, "bold", TEXT)]


def test_display_sizes_selected_takes_latest_size():
    out = layout.display_sizes(6, 52, 0.75, 0)
    assert out[0] == (52, "bold", TEXT)
    # 선택이 있으면 최신 문장은 앞 문장 크기가 된다
    assert out[-1] == (39, "bold", RECENT)
    assert out[1] == (31, "normal", MUTED)


def test_display_sizes_selected_minus_one_means_none():
    assert layout.display_sizes(3, 52, 0.75, -1) == layout.display_sizes(3, 52, 0.75, None)


def test_display_sizes_minimum_18():
    out = layout.display_sizes(6, 24, 0.55, None)
    assert out[-2][0] == 18  # round(24*0.55)=13 -> 18
    assert out[0][0] == 18
    assert out[-1][0] == 24


def test_clamp_font():
    assert layout.clamp_font(10) == 24
    assert layout.clamp_font(24) == 24
    assert layout.clamp_font(52) == 52
    assert layout.clamp_font(120) == 120
    assert layout.clamp_font(500) == 120


def test_step_font():
    assert layout.step_font(52, +1) == 60
    assert layout.step_font(52, -1) == 44
    assert layout.step_font(116, +1) == 120
    assert layout.step_font(28, -1) == 24


def test_prev_scales():
    assert layout.PREV_SCALES == {"작게": 0.55, "보통": 0.75, "크게": 0.9}


def test_status_text_online():
    assert (layout.status_text(True, "MyMemory", None, 600)
            == "온라인 · 인식 Zipformer · 번역 MyMemory · 메모리 0.6GB")


def test_status_text_fallback_reasons():
    assert "번역 NLLB (한도 초과)" in layout.status_text(True, "NLLB-600M", "quota", 900)
    assert "번역 NLLB (오류)" in layout.status_text(True, "NLLB-600M", "error", 900)


def test_status_text_offline():
    s = layout.status_text(False, "NLLB-600M", "offline", 1536)
    assert s == "오프라인 · 인식 Zipformer · 번역 NLLB · 메모리 1.5GB"


def test_mic_bar_fraction():
    assert layout.mic_bar_fraction(-120) == 0.0
    assert layout.mic_bar_fraction(-30) == 0.5
    assert layout.mic_bar_fraction(3) == 1.0


def test_check_direct_input():
    assert layout.check_direct_input("  ") is not None
    assert layout.check_direct_input("가" * 500) is None
    assert "500자" in layout.check_direct_input("가" * 501)
    assert layout.check_direct_input("안녕하세요") is None


def test_status_text_no_engine_yet():
    assert "번역 MyMemory" in layout.status_text(True, None, None, 100)
    assert "번역 NLLB" in layout.status_text(False, None, None, 100)
