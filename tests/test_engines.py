import json

import pytest

from sukpago import paths
from sukpago.engines import ModelManager, load_engines, parse_engines

VALID = {"asr": "zipformer", "offline_mt": {"mn": "hymt", "zh": "hymt", "en": "nllb"}}


def test_parse_valid():
    cfg = parse_engines(VALID)
    assert cfg.asr == "zipformer"
    assert cfg.offline_mt == {"mn": "hymt", "zh": "hymt", "en": "nllb"}


@pytest.mark.parametrize("data,msg", [
    ({**VALID, "asr": "whisper"}, "asr"),
    ({"asr": "zipformer", "offline_mt": {"mn": "hymt", "zh": "hymt"}}, "빠졌습니다"),
    ({"asr": "zipformer", "offline_mt": {"mn": "gpt", "zh": "hymt", "en": "hymt"}}, "알 수 없는"),
])
def test_parse_invalid(data, msg):
    with pytest.raises(ValueError, match=msg):
        parse_engines(data)


def test_repo_engines_json_is_valid():
    load_engines(paths.assets_dir() / "engines.json")


def test_load_from_file(tmp_path):
    p = tmp_path / "engines.json"
    p.write_text(json.dumps(VALID), encoding="utf-8")
    assert load_engines(p).offline_mt["en"] == "nllb"


class FakeEngine:
    def __init__(self, name, log):
        self.name, self.log = name, log
        log.append(f"make {name}")

    def translate(self, text, lang):
        return f"{self.name}:{text}"

    def unload(self):
        self.log.append(f"unload {self.name}")


def test_model_manager_keeps_one_loaded():
    log = []
    mm = ModelManager({"hymt": lambda: FakeEngine("hymt", log), "nllb": lambda: FakeEngine("nllb", log)})
    a = mm.get("hymt")
    assert mm.get("hymt") is a
    mm.get("nllb")
    assert log == ["make hymt", "unload hymt", "make nllb"]
    assert mm.active_name == "nllb"
    mm.unload()
    assert log[-1] == "unload nllb" and mm.active_name is None


def test_model_manager_unknown():
    with pytest.raises(KeyError):
        ModelManager({}).get("hymt")


def test_make_router_online_engine(tmp_path):
    from sukpago.engines import make_router
    r = make_router("me@example.com", tmp_path / "models")
    assert r._online.name == "MyMemory"
    assert r._online.email == "me@example.com"
    assert r._offline_for == {"mn": "nllb600", "zh": "nllb600", "en": "nllb600"}


def test_make_router_offline_engine_is_lazy(tmp_path, monkeypatch):
    from sukpago import engines
    from sukpago.translate import nllb

    made = []

    class FakeNllb:
        name = "NLLB-600M"

        def __init__(self, model_dir):
            made.append(model_dir)

        def translate(self, text, lang):
            return f"nllb:{lang}:{text}"

    monkeypatch.setattr(nllb, "NllbTranslator", FakeNllb)
    r = engines.make_router("me@example.com", tmp_path / "models")
    assert made == [] and r._models.active_name is None
    res = r.translate("안녕", "mn", online=False)
    assert res.text == "nllb:mn:안녕" and res.engine == "NLLB-600M"
    assert made == [tmp_path / "models" / "nllb-600m"]
    r.translate("안녕", "zh", online=False)
    assert len(made) == 1
