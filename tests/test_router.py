import pytest

from sukpago.engines import ModelManager
from sukpago.translate.base import QuotaExceeded, TranslateError
from sukpago.translate.router import RouteResult, TranslateRouter


class Eng:
    def __init__(self, name, fail=None):
        self.name, self.fail, self.calls = name, fail, []

    def translate(self, text, lang):
        self.calls.append((text, lang))
        if self.fail:
            raise self.fail
        return f"{self.name}:{lang}:{text}"


def router(online, offline_engines):
    mm = ModelManager({name: (lambda e=e: e) for name, e in offline_engines.items()})
    return TranslateRouter(online, mm, {"mn": "nllb", "zh": "hymt", "en": "hymt"})


def test_online_success():
    r = router(Eng("MyMemory"), {"hymt": Eng("Hy"), "nllb": Eng("NL")})
    assert r.translate("안녕", "zh", online=True) == RouteResult("MyMemory:zh:안녕", "MyMemory", False)


@pytest.mark.parametrize("err", [TranslateError("down"), QuotaExceeded("quota")])
def test_online_failure_falls_back(err):
    r = router(Eng("MyMemory", fail=err), {"hymt": Eng("Hy"), "nllb": Eng("NL")})
    assert r.translate("안녕", "mn", online=True) == RouteResult("NL:mn:안녕", "NL", True)


def test_offline_mode_uses_per_language_engine():
    online = Eng("MyMemory")
    r = router(online, {"hymt": Eng("Hy"), "nllb": Eng("NL")})
    assert r.translate("안녕", "en", online=False) == RouteResult("Hy:en:안녕", "Hy", False)
    assert online.calls == []


def test_no_online_engine_means_offline():
    r = router(None, {"hymt": Eng("Hy"), "nllb": Eng("NL")})
    assert r.translate("안녕", "zh", online=True).fell_back is False


def test_offline_failure_propagates():
    r = router(Eng("MyMemory", fail=TranslateError("x")),
               {"hymt": Eng("Hy", fail=TranslateError("y")), "nllb": Eng("NL")})
    with pytest.raises(TranslateError, match="y"):
        r.translate("안녕", "zh", online=True)
