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
    a = SentenceAssembler(max_chars=20, hold_unfinished_chars=0)
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


def test_feed_now_does_not_wait_and_takes_pending():
    a = SentenceAssembler()
    assert a.feed("그렇죠", 0.0) == []  # 짧아서 붙잡아 둠
    assert a.feed_now("내용은 크게 달라지지 않았는데") == ["그렇죠 내용은 크게 달라지지 않았는데"]
    assert a.flush() == []


def test_short_unfinished_piece_is_held_and_merged():
    a = SentenceAssembler()
    assert a.feed("여러분들이 피씨에", 0.0) == []
    a.still_talking(2.9)
    assert a.tick(4.0) == []  # 아직 말하는 중이면 기다림
    assert a.feed("크롬에 확장 프로그램을 설치해야 됩니다", 5.0) == ["여러분들이 피씨에 크롬에 확장 프로그램을 설치해야 됩니다"]


def test_finished_short_sentence_is_not_held():
    a = SentenceAssembler()
    assert a.feed("이해됐나요 여러분 질문 있어요", 0.0) == ["이해됐나요 여러분 질문 있어요"]


def test_split_off_particle_is_glued_back():
    a = SentenceAssembler()
    assert a.feed("여러분들이 보고서", 0.0, cut=True) == []
    assert a.feed("를 작성을 하겠죠", 1.0) == ["여러분들이 보고서를 작성을 하겠죠"]


def test_ambiguous_standalone_word_is_not_glued():
    a = SentenceAssembler()
    assert a.feed("참석한 사람이", 0.0) == []
    assert a.feed("만 명이 넘었어요", 1.0) == ["참석한 사람이 만 명이 넘었어요"]


def test_particle_e_is_kept_when_piece_was_held():
    a = SentenceAssembler()
    assert a.feed("이번 보고서", 0.0, cut=True) == []
    assert a.feed("에 대해서 설명할게요", 1.0) == ["이번 보고서에 대해서 설명할게요"]
    assert a.feed("에 그러니까 다음은 실습입니다", 2.0) == ["그러니까 다음은 실습입니다"]  # 앞 조각이 없으면 군말


def test_held_piece_is_released_after_max_hold_even_while_talking():
    a = SentenceAssembler(max_hold_s=8.0)
    assert a.feed("여러분들이 피씨에", 0.0) == []
    for t in (2.0, 4.0, 6.0):
        a.still_talking(t)
        assert a.tick(t) == []
    a.still_talking(8.0)
    assert a.tick(8.0) == ["여러분들이 피씨에"]



def test_filler_e_after_held_piece_is_not_glued():
    a = SentenceAssembler()
    assert a.feed("오늘 배울 내용은", 0.0) == []
    assert a.feed("에 그러니까 데이터베이스 정규화입니다", 1.0) == ["오늘 배울 내용은 그러니까 데이터베이스 정규화입니다"]
    a = SentenceAssembler()
    assert a.feed("자 이제 다 같이 실습실로", 0.0, cut=True) == []
    assert a.feed("가 봅시다", 1.0) == ["자 이제 다 같이 실습실로 가 봅시다"]


def test_long_forced_cut_is_held_and_glued():
    a = SentenceAssembler()
    long = "그러면 수업시간에 교수님이 요구하는 주제 요구하는 양식에 맞춰서 여러분들이 제출해야 하는 보고서"
    assert a.feed(long, 0.0, cut=True) == []
    assert a.feed("를 작성을 하겠죠", 1.0) == [long + "를 작성을 하겠죠"]


def test_glossary_rule_spanning_held_pieces_is_applied():
    a = SentenceAssembler(Glossary([Rule("쿠버 네티스", "쿠버네티스")]))
    assert a.feed("이번 시간에는 쿠버", 0.0) == []
    assert a.feed("네티스를 설치하겠습니다", 1.0) == ["이번 시간에는 쿠버네티스를 설치하겠습니다"]


def test_merged_piece_restarts_wait():
    a = SentenceAssembler(wait_s=3.0)
    a.feed("여러분들이", 0.0)
    a.feed("피씨에서", 2.5)
    assert a.tick(4.0) == []
    assert a.tick(5.5) == ["여러분들이 피씨에서"]



def test_e_after_word_ending_in_particle_is_dropped_as_filler():
    a = SentenceAssembler()
    assert a.feed("이번 시간에 다룰 내용은", 0.0, cut=True) == []
    assert a.feed("에 그러니까 람다 함수입니다", 1.0) == ["이번 시간에 다룰 내용은 그러니까 람다 함수입니다"]


def test_particle_glued_after_noun_whose_last_syllable_looks_like_particle():
    for left, right, want in [("실행한 결과", "를 보면 정렬됩니다", "실행한 결과를 보면 정렬됩니다"),
                              ("알고리즘의 속도", "가 빨라집니다", "알고리즘의 속도가 빨라집니다")]:
        a = SentenceAssembler()
        assert a.feed(left, 0.0, cut=True) == []
        assert a.feed(right, 1.0) == [want]


def test_lone_particle_e_after_cut_is_kept():
    a = SentenceAssembler()
    assert a.feed("이번 과제는 요구사항", 0.0, cut=True) == []
    assert a.feed_now("에 맞추어") == ["이번 과제는 요구사항에 맞추어"]



def test_lone_particle_e_alone_after_cut_is_kept():
    a = SentenceAssembler()
    assert a.feed("이번 학기 보고서", 0.0, cut=True) == []
    assert a.feed("에", 0.5) == []
    assert a.flush() == ["이번 학기 보고서에"]



def test_particle_with_punctuation_after_cut_is_kept():
    a = SentenceAssembler()
    assert a.feed("우리가 만든 운영 체제의 파일 시스템", 0.0, cut=True) == []
    assert a.feed("에.", 1.0) == []
    assert a.flush() == ["우리가 만든 운영 체제의 파일 시스템에."]



def test_word_starting_like_copula_is_not_glued():
    for left, right, want in [("바꾸게 되었고 특히", "이라크와 아프가니스탄에서 철수했습니다", "바꾸게 되었고 특히 이라크와 아프가니스탄에서 철수했습니다"),
                              ("오늘은 여기까지 하고", "이다음 시간에는 실습입니다", "오늘은 여기까지 하고 이다음 시간에는 실습입니다"),
                              ("중요한 것은 독자의 관점", "이라는 거죠", "중요한 것은 독자의 관점이라는 거죠")]:
        a = SentenceAssembler()
        assert a.feed(left, 0.0, cut=True) == []
        assert a.feed(right, 1.0) == [want]



def test_copula_matches_whole_endings_only():
    from sukpago.text.clauses import COPULA
    for w in ("이라고요", "이라는데", "이라고는", "이라든가", "이라서요", "이라니", "이라", "이다", "이고요", "이었습니다", "입니다."):
        assert COPULA.match(w), w
    for w in ("이라크", "이라크인", "이다음"):
        assert not COPULA.match(w), w



def test_copula_variants_glue_but_verb_after_particle_does_not():
    for left, right, want in [("그건 지도 학습", "이지만 많이 쓰여요", "그건 지도 학습이지만 많이 쓰여요"),
                              ("그래서 두 점을 선으로", "이었습니다", "그래서 두 점을 선으로 이었습니다")]:
        a = SentenceAssembler()
        assert a.feed(left, 0.0, cut=True) == []
        assert a.feed(right, 1.0) + a.flush() == [want]



def test_copula_glues_after_noun_ending_in_ro():
    for left, right, want in [("그래서 이게 바로 최단 경로", "입니다", "그래서 이게 바로 최단 경로입니다"),
                              ("이 부분이 전자 회로", "이고요 다음은 전원이에요", "이 부분이 전자 회로이고요 다음은 전원이에요")]:
        a = SentenceAssembler()
        assert a.feed(left, 0.0, cut=True) == []
        assert a.feed(right, 1.0) + a.flush() == [want]
