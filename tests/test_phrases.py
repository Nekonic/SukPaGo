import json

import pytest

from sukpago import paths, phrases
from sukpago.languages import TARGET_ORDER


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("SUKPAGO_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def test_fixed_phrases_in_order():
    fixed = phrases.load_all()
    assert [p.key for p in fixed] == ["p1", "p2", "p3", "p4", "p5"]
    assert [p.ko for p in fixed] == ["떠들지 마세요.", "집중하세요.", "이해됐나요?", "질문 있나요?",
                                     "질문 없으면 넘어갈게요."]
    assert all(set(p.texts) == set(TARGET_ORDER) for p in fixed)
    assert fixed[1].texts == {"mn": "Анхаарлаа төвлөрүүл.", "zh": "请集中注意力。", "en": "Please focus."}


def test_assets_file_shape():
    data = json.loads((paths.assets_dir() / "phrases.json").read_text(encoding="utf-8"))
    assert all(set(d) == {"key", "ko", "mn", "zh", "en"} for d in data)


def test_audio_path(home):
    fixed = phrases.load_all()[0]
    assert phrases.audio_path(fixed, "mn") == paths.assets_dir() / "phrases" / "p1_mn.mp3"
