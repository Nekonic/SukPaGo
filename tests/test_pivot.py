from sukpago.translate.pivot import PivotTranslator


class Eng:
    name = "E"

    def __init__(self):
        self.calls, self.unloaded = [], False

    def translate(self, text, lang, src="ko"):
        self.calls.append((text, lang, src))
        return f"{src}>{lang}:{text}"

    def unload(self):
        self.unloaded = True


def test_mongolian_goes_through_english():
    e = Eng()
    p = PivotTranslator(e, name="E-pivot")
    assert p.translate("안녕", "mn") == "en>mn:ko>en:안녕"
    assert e.calls == [("안녕", "en", "ko"), ("ko>en:안녕", "mn", "en")]
    assert p.name == "E-pivot"


def test_other_languages_are_direct():
    e = Eng()
    p = PivotTranslator(e, name="E-pivot")
    assert p.translate("안녕", "zh") == "ko>zh:안녕"
    assert p.translate("안녕", "en") == "ko>en:안녕"


def test_unload_passes_through():
    e = Eng()
    PivotTranslator(e, name="x").unload()
    assert e.unloaded
