import json

import pytest

from sukpago import paths, phrases
from sukpago.languages import TARGET_ORDER
from sukpago.phrases import Phrase


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("SUKPAGO_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def test_fixed_phrases_in_order():
    fixed = phrases.load_all()
    assert [p.key for p in fixed] == ["p1", "p2", "p3", "p4", "p5"]
    assert [p.ko for p in fixed] == ["떠들지 마세요.", "집중하세요.", "이해됐나요?", "질문 있나요?",
                                     "질문 없으면 넘어갈게요."]
    assert all(not p.custom and set(p.texts) == set(TARGET_ORDER) for p in fixed)
    assert fixed[1].texts == {"mn": "Анхаарлаа төвлөрүүл.", "zh": "请集中注意力。", "en": "Please focus."}


def test_assets_file_shape():
    data = json.loads((paths.assets_dir() / "phrases.json").read_text(encoding="utf-8"))
    assert all(set(d) == {"key", "ko", "mn", "zh", "en"} for d in data)


def test_add_custom_appears_after_fixed():
    p = phrases.add_custom("  책 펴세요.  ", {"mn": "Номоо нээгээрэй.", "en": "Open your books."})
    assert p.key.startswith("c") and len(p.key) == 14 and p.key[1:].isdigit()
    assert p.custom is True and p.ko == "책 펴세요."
    allp = phrases.load_all()
    assert [x.key for x in allp][:5] == ["p1", "p2", "p3", "p4", "p5"]
    assert allp[-1] == p


def test_add_custom_keys_unique():
    a = phrases.add_custom("하나", {"en": "one"})
    b = phrases.add_custom("둘", {"en": "two"})
    assert a.key != b.key
    assert [x.ko for x in phrases.load_all() if x.custom] == ["하나", "둘"]


def test_add_custom_rejects_empty():
    with pytest.raises(ValueError):
        phrases.add_custom("   ", {"en": "x"})


def test_remove_custom_deletes_json_and_mp3(home):
    keep = phrases.add_custom("남길 문장", {"en": "keep"})
    p = phrases.add_custom("지울 문장", {"mn": "a", "en": "b"})
    for lang in ("mn", "en"):
        f = phrases.audio_path(p, lang)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"ID3fake")
    other = phrases.audio_path(keep, "en")
    other.write_bytes(b"ID3keep")
    phrases.remove_custom(p.key)
    assert [x.key for x in phrases.load_all() if x.custom] == [keep.key]
    assert not phrases.audio_path(p, "mn").exists() and not phrases.audio_path(p, "en").exists()
    assert other.exists()


def test_remove_unknown_is_noop():
    phrases.remove_custom("c0000000000000")
    assert len(phrases.load_all()) == 5


def test_audio_path(home):
    fixed = phrases.load_all()[0]
    assert phrases.audio_path(fixed, "mn") == paths.assets_dir() / "phrases" / "p1_mn.mp3"
    mine = Phrase("c1732500000000", "내 문장", {"zh": "我"}, True)
    assert phrases.audio_path(mine, "zh") == home / "phrases" / "c1732500000000_zh.mp3"


def test_broken_custom_file_ignored(home):
    home.mkdir(parents=True, exist_ok=True)
    (home / "custom_phrases.json").write_text("[{\"nope\": 1}, 3]", encoding="utf-8")
    assert len(phrases.load_all()) == 5
