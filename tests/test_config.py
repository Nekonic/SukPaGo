import json

import pytest

from sukpago import config, userdata
from sukpago.config import Settings
from sukpago.text.glossary import Glossary


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("SUKPAGO_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def test_defaults():
    s = config.load_settings()
    assert s == Settings()
    assert s.mymemory_email == "abcd@gmail.com"
    assert s.online is True and s.langs == ["mn", "zh"]
    assert s.display_font_px == 52
    assert s.main_geometry is None and s.display_geometry is None


def test_save_load_roundtrip():
    s = Settings(online=False, langs=["en"], mymemory_email="x@y.z", main_geometry="800x600+10+20",
                 display_geometry="1200x400+0+0", display_font_px=80)
    config.save_settings(s)
    assert config.load_settings() == s


def test_unknown_keys_ignored_and_bad_values_default():
    userdata.write_json("settings.json", {"display_font_px": "big", "online": False, "whatever": 1,
                                          "langs": "mn", "main_geometry": 3})
    s = config.load_settings()
    assert s.display_font_px == 52
    assert s.online is False
    assert s.langs == ["mn", "zh"]
    assert s.main_geometry is None


def test_bool_is_not_int():
    userdata.write_json("settings.json", {"display_font_px": True, "online": 1})
    s = config.load_settings()
    assert s.display_font_px == 52 and s.online is True


def test_bad_langs_default():
    userdata.write_json("settings.json", {"langs": ["mn", "fr"]})
    assert config.load_settings().langs == ["mn", "zh"]
    userdata.write_json("settings.json", {"langs": []})
    assert config.load_settings().langs == ["mn", "zh"]


def test_non_dict_file_gives_defaults():
    userdata.write_json("settings.json", [1, 2])
    assert config.load_settings() == Settings()


def test_glossary_default_rules():
    g = config.load_glossary()
    assert [(r.wrong, r.right) for r in g.rules] == [("노트북 에램", "NotebookLM"),
                                                    ("한강 리스크", "할루시네이션 리스크")]


def test_glossary_roundtrip(home):
    g = Glossary()
    g.add("클로드", "Claude")
    config.save_glossary(g)
    assert config.load_glossary().to_json() == [{"wrong": "클로드", "right": "Claude"}]
    assert json.loads((home / "glossary.json").read_text(encoding="utf-8")) == g.to_json()


def test_broken_glossary_gives_default():
    userdata.write_json("glossary.json", [{"oops": 1}])
    assert len(config.load_glossary().rules) == 2
