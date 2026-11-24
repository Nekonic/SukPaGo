import re

import pytest

from sukpago.asr.base import SAMPLE_RATE, load_wav_16k_mono

HANGUL = re.compile(r"[가-힣]")


def run(rec, samples):
    finals = []
    step = SAMPLE_RATE // 10
    for i in range(0, len(samples), step):
        finals += [e.text for e in rec.accept(samples[i:i + step]) if e.kind == "final"]
    finals += [e.text for e in rec.finish() if e.kind == "final"]
    return " ".join(finals)


@pytest.mark.models
def test_zipformer_recognizes_korean(model_path):
    from sukpago.asr.zipformer import ZipformerRecognizer

    wav = model_path("sensevoice", "test_wavs", "ko.wav")
    rec = ZipformerRecognizer(model_path("zipformer-ko"))
    text = run(rec, load_wav_16k_mono(wav))
    assert HANGUL.search(text), text
    # sherpa-onnx 1.13.x는 한글 사이 공백을 지우는 버그가 있어 토큰에서 복원한다
    assert re.search(r"[가-힣] [가-힣]", text), text


@pytest.mark.models
def test_zipformer_emits_partials(model_path):
    from sukpago.asr.zipformer import ZipformerRecognizer

    samples = load_wav_16k_mono(model_path("sensevoice", "test_wavs", "ko.wav"))
    rec = ZipformerRecognizer(model_path("zipformer-ko"))
    kinds = set()
    for i in range(0, len(samples), SAMPLE_RATE // 10):
        kinds |= {e.kind for e in rec.accept(samples[i:i + SAMPLE_RATE // 10])}
    assert "partial" in kinds


@pytest.mark.models
def test_sensevoice_recognizes_korean(model_path):
    from sukpago.asr.sensevoice import SenseVoiceRecognizer

    rec = SenseVoiceRecognizer(model_path("sensevoice"), model_path("vad", "silero_vad.onnx"))
    text = run(rec, load_wav_16k_mono(model_path("sensevoice", "test_wavs", "ko.wav")))
    assert HANGUL.search(text), text
