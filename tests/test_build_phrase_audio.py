import json

import build_phrase_audio as bpa
from sukpago.tts.base import TtsError

PHRASES = [
    {"key": "p1", "ko": "집중해 주세요.", "mn": "Анхаарлаа төвлөрүүл.", "zh": "请集中注意力。", "en": "Please focus."},
    {"key": "p2", "ko": "쉬는 시간입니다.", "mn": "Завсарлага.", "zh": "休息时间。", "en": "Break time."},
]


class FakeSpeaker:
    name = "fake"

    def __init__(self, fail_after=None):
        self.calls = []
        self.fail_after = fail_after

    def synth(self, text, lang):
        if self.fail_after is not None and len(self.calls) >= self.fail_after:
            raise TtsError("no internet")
        self.calls.append((text, lang))
        return f"mp3:{text}".encode()


def write_phrases(tmp_path):
    f = tmp_path / "phrases.json"
    f.write_text(json.dumps(PHRASES, ensure_ascii=False), encoding="utf-8")
    return f


def test_builds_every_phrase_and_language(tmp_path):
    out = tmp_path / "out"
    sp = FakeSpeaker()
    assert bpa.main(speaker=sp, phrases_file=write_phrases(tmp_path), out_dir=out) == 0
    names = sorted(p.name for p in out.iterdir())
    assert names == sorted(f"{k}_{l}.mp3" for k in ("p1", "p2") for l in ("mn", "zh", "en"))
    assert (out / "p1_mn.mp3").read_bytes() == "mp3:Анхаарлаа төвлөрүүл.".encode()
    assert ("Please focus.", "en") in sp.calls
    assert len(sp.calls) == 6


def test_skips_existing_files(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "p1_mn.mp3").write_bytes(b"old")
    sp = FakeSpeaker()
    bpa.main(speaker=sp, phrases_file=write_phrases(tmp_path), out_dir=out)
    assert (out / "p1_mn.mp3").read_bytes() == b"old"
    assert ("Анхаарлаа төвлөрүүл.", "mn") not in sp.calls
    assert len(sp.calls) == 5


def test_network_failure_warns_and_exits_zero(tmp_path, capsys):
    out = tmp_path / "out"
    sp = FakeSpeaker(fail_after=2)
    assert bpa.main(speaker=sp, phrases_file=write_phrases(tmp_path), out_dir=out) == 0
    assert "경고" in capsys.readouterr().err
    assert len(list(out.glob("*.mp3"))) == 2
    assert not list(out.glob("*.tmp"))


def test_missing_phrases_file_is_error(tmp_path, capsys):
    sp = FakeSpeaker()
    assert bpa.main(speaker=sp, phrases_file=tmp_path / "none.json",
                    out_dir=tmp_path / "out") == 1
    assert "오류" in capsys.readouterr().err
    assert sp.calls == []
