import pytest

from sukpago import userdata


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("SUKPAGO_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def test_home_uses_env_and_creates(home):
    assert userdata.home() == home
    assert home.is_dir()


def test_roundtrip_keeps_korean(home):
    userdata.write_json("x.json", {"말": "노트북 에램", "n": [1, 2]})
    assert userdata.read_json("x.json", None) == {"말": "노트북 에램", "n": [1, 2]}
    assert "노트북 에램" in (home / "x.json").read_text(encoding="utf-8")


def test_missing_returns_default():
    assert userdata.read_json("none.json", {"a": 1}) == {"a": 1}


def test_broken_json_returns_default(home):
    userdata.home()
    (home / "bad.json").write_text("{not json", encoding="utf-8")
    assert userdata.read_json("bad.json", []) == []


def test_write_leaves_no_temp_files(home):
    userdata.write_json("a.json", [1])
    userdata.write_json("a.json", [2])
    assert sorted(p.name for p in home.iterdir()) == ["a.json"]
    assert userdata.read_json("a.json", None) == [2]
