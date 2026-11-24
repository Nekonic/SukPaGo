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
