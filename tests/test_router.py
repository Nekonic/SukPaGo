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


@pytest.mark.parametrize("err,reason", [(TranslateError("down"), "error"), (QuotaExceeded("quota"), "quota")])
def test_online_failure_falls_back(err, reason):
    r = router(Eng("MyMemory", fail=err), {"hymt": Eng("Hy"), "nllb": Eng("NL")})
    assert r.translate("안녕", "mn", online=True) == RouteResult("NL:mn:안녕", "NL", True, reason)


def test_offline_mode_uses_per_language_engine():
    online = Eng("MyMemory")
    r = router(online, {"hymt": Eng("Hy"), "nllb": Eng("NL")})
    assert r.translate("안녕", "en", online=False) == RouteResult("Hy:en:안녕", "Hy", False, "offline")
    assert online.calls == []


def test_no_online_engine_means_offline():
    r = router(None, {"hymt": Eng("Hy"), "nllb": Eng("NL")})
    res = r.translate("안녕", "zh", online=True)
    assert res.fell_back is False and res.reason == "offline"


def test_offline_failure_propagates():
    r = router(Eng("MyMemory", fail=TranslateError("x")),
               {"hymt": Eng("Hy", fail=TranslateError("y")), "nllb": Eng("NL")})
    with pytest.raises(TranslateError, match="y"):
        r.translate("안녕", "zh", online=True)


def test_reason_defaults_to_none():
    assert RouteResult("a", "b", False).reason is None


def test_quota_skips_online_until_reset():
    online = Eng("MyMemory", fail=QuotaExceeded("quota"))
    r = router(online, {"hymt": Eng("Hy"), "nllb": Eng("NL")})
    assert r.quota_exceeded is False
    r.translate("하나", "zh", online=True)
    assert r.quota_exceeded is True and len(online.calls) == 1
    res = r.translate("둘", "en", online=True)
    assert res == RouteResult("Hy:en:둘", "Hy", True, "quota")
    assert len(online.calls) == 1
    online.fail = None
    r.reset_quota()
    assert r.quota_exceeded is False
    assert r.translate("셋", "zh", online=True) == RouteResult("MyMemory:zh:셋", "MyMemory", False)
    assert len(online.calls) == 2


def test_quota_does_not_affect_offline_mode():
    r = router(Eng("MyMemory", fail=QuotaExceeded("quota")), {"hymt": Eng("Hy"), "nllb": Eng("NL")})
    r.translate("하나", "zh", online=True)
    assert r.translate("둘", "zh", online=False) == RouteResult("Hy:zh:둘", "Hy", False, "offline")


def test_plain_error_only_affects_that_request():
    online = Eng("MyMemory", fail=TranslateError("down"))
    r = router(online, {"hymt": Eng("Hy"), "nllb": Eng("NL")})
    assert r.translate("하나", "zh", online=True).reason == "error"
    assert r.quota_exceeded is False
    online.fail = None
    assert r.translate("둘", "zh", online=True) == RouteResult("MyMemory:zh:둘", "MyMemory", False)
    assert len(online.calls) == 2
