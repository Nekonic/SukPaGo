from sukpago.text.assembler import SentenceAssembler
from sukpago.text.glossary import Glossary, Rule


def test_filler_only_segment_is_dropped():
    a = SentenceAssembler()
    assert a.feed("어.", 0) == []
    assert a.feed("네 네", 1) == []
    assert a.flush() == []


def test_leading_and_trailing_fillers_removed_but_determiner_kept():
    a = SentenceAssembler()
    assert a.feed("음 오늘은 광합성을 배울 거예요 어", 0) == ["오늘은 광합성을 배울 거예요"]
    assert a.feed("그 사람은 과학자였습니다", 1) == ["그 사람은 과학자였습니다"]


def test_stutter_and_repeated_words_collapsed():
    assert SentenceAssembler().clean("여러분러분 많이 많이 들어 보셨죠") == "여러분 많이 들어 보셨죠"


def test_reduplicated_words_are_kept():
    text = "별이 반짝반짝 하나하나 빛나요"
    assert SentenceAssembler().clean(text) == text


def test_short_fragment_waits_for_next():
    a = SentenceAssembler()
    assert a.feed("교과서", 0.0) == []
    assert a.feed("사십오 쪽 펴 주세요", 1.0) == ["교과서 사십오 쪽 펴 주세요"]


def test_short_fragment_flushed_after_wait():
    a = SentenceAssembler(wait_s=3.0)
    assert a.feed("그렇구나", 10.0) == []
    assert a.tick(12.0) == []
    assert a.tick(13.0) == ["그렇구나"]
    assert a.tick(20.0) == []


def test_long_text_split_at_endings_within_limit():
    a = SentenceAssembler(max_chars=40)
    text = ("오늘은 광합성에 대해 배울 거예요 식물은 햇빛과 물을 이용해서 양분을 만들어요 "
            "다음 주까지 숙제를 내세요")
    out = a.feed(text, 0)
    assert out == [
        "오늘은 광합성에 대해 배울 거예요",
        "식물은 햇빛과 물을 이용해서 양분을 만들어요 다음 주까지 숙제를 내세요",
    ]
    assert all(len(s) <= 40 for s in out)


def test_very_long_piece_without_endings_is_wrapped_at_spaces():
    a = SentenceAssembler(max_chars=20)
    text = "가나다 라마바 사아자 차카타 파하가 나다라 마바사"
    out = a.feed(text, 0)
    assert all(len(s) <= 20 for s in out)
    assert " ".join(out) == text


def test_glossary_applied():
    a = SentenceAssembler(Glossary([Rule("노트북 에램", "NotebookLM")]))
    assert a.feed("노트북 에램 이라는 사이트가 있어요", 0) == ["NotebookLM 이라는 사이트가 있어요"]


def test_numbers_and_latin_are_not_collapsed():
    a = SentenceAssembler()
    assert a.clean("전화번호는 121212 이고 202020 입니다") == "전화번호는 121212 이고 202020 입니다"
    assert a.clean("bookbookbook 은 그대로") == "bookbookbook 은 그대로"
    assert a.clean("여러분러분 안녕하세요") == "여러분 안녕하세요"
