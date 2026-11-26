from sukpago.text.clauses import ClauseCommitter


def test_commits_clause_once_the_word_after_it_is_stable():
    c = ClauseCommitter(sentence_chars=10, clause_chars=10)
    assert c.partial("내용은 크게 달라진 것 같지는 않은데") == []
    assert c.partial("내용은 크게 달라진 것 같지는 않은데 이제") == []  # '이제'가 아직 한 번만 나옴
    assert c.partial("내용은 크게 달라진 것 같지는 않은데 이제 뒤에") == ["내용은 크게 달라진 것 같지는 않은데"]
    assert c.final("내용은 크게 달라진 것 같지는 않은데 이제 뒤에 실습은 바뀌어요") == "이제 뒤에 실습은 바뀌어요"


def test_unstable_prefix_is_not_committed():
    c = ClauseCommitter(sentence_chars=10, clause_chars=10)
    c.partial("병원을 여러 군데 보는데 학교")
    assert c.partial("병원은 여러 군데 보는데 학교에서") == []


def test_aux_verb_and_dependent_noun_are_not_boundaries():
    c = ClauseCommitter(sentence_chars=10, clause_chars=10)
    c.partial("이렇게도 해보려고 하고 있습니다 그래서")
    assert c.partial("이렇게도 해보려고 하고 있습니다 그래서 강의") == ["이렇게도 해보려고 하고 있습니다"]
    c = ClauseCommitter(sentence_chars=10, clause_chars=10)
    c.partial("이게 정말 중요한 거라서 하는 것 같아요 다음")
    assert c.partial("이게 정말 중요한 거라서 하는 것 같아요 다음 시간") == ["이게 정말 중요한 거라서 하는 것 같아요"]


def test_short_clause_waits():
    c = ClauseCommitter(sentence_chars=10, clause_chars=10)
    c.partial("네 그렇죠 그래서")
    assert c.partial("네 그렇죠 그래서 오늘은") == []


def test_commits_progressively_and_final_returns_rest_then_resets():
    c = ClauseCommitter(sentence_chars=10, clause_chars=10)
    c.partial("첫 번째 내용을 설명했는데 두 번째는")
    assert c.partial("첫 번째 내용을 설명했는데 두 번째는 조금") == ["첫 번째 내용을 설명했는데"]
    c.partial("첫 번째 내용을 설명했는데 두 번째는 조금 어려워요 그러니까")
    assert c.partial("첫 번째 내용을 설명했는데 두 번째는 조금 어려워요 그러니까 천천히") == ["두 번째는 조금 어려워요"]
    assert c.final("첫 번째 내용을 설명했는데 두 번째는 조금 어려워요 그러니까 천천히 할게요") == "그러니까 천천히 할게요"
    assert c.final("다음 발화") == "다음 발화"


def test_default_needs_long_clause_but_shorter_sentence():
    c = ClauseCommitter()
    c.partial("내용은 크게 달라진 것 같지는 않은데 이제")
    assert c.partial("내용은 크게 달라진 것 같지는 않은데 이제 뒤에") == []  # 절 끝인데 16자뿐
    c = ClauseCommitter()
    c.partial("내용은 크게 달라지지 않았다고 봅니다 이제")
    assert c.partial("내용은 크게 달라지지 않았다고 봅니다 이제 뒤에") == ["내용은 크게 달라지지 않았다고 봅니다"]


def committed(c, words):
    """partial 두 번으로 앞 절을 내보낸다."""
    c.partial(words + " 다음")
    return c.partial(words + " 다음 말")


def test_final_with_different_spacing_cuts_by_characters():
    c = ClauseCommitter(sentence_chars=5, clause_chars=5)
    assert committed(c, "보고서를 작성해야 하는데") == ["보고서를 작성해야 하는데"]
    # 확정에서 어절이 갈라져도("작성 해야") 겹치거나 빠지지 않는다
    assert c.final("보고서를 작성 해야 하는데 다음 말을 해요") == "다음 말을 해요"
    assert committed(c, "보고서를 작성 해야 하는데") == ["보고서를 작성 해야 하는데"]
    assert c.final("보고서를 작성해야하는데 다음 말을 해요") == "다음 말을 해요"


def test_standalone_noun_or_adverb_is_not_a_sentence_end():
    c = ClauseCommitter(sentence_chars=5, clause_chars=99)
    c.partial("이 단계는 사실 별로 필요 없는 과정이에요 그래서")
    assert c.partial("이 단계는 사실 별로 필요 없는 과정이에요 그래서 다음") == ["이 단계는 사실 별로 필요 없는 과정이에요"]
    c = ClauseCommitter(sentence_chars=5, clause_chars=99)
    c.partial("그러면 우리 다 같이")
    assert c.partial("그러면 우리 다 같이 해볼까") == []



def test_common_nouns_ending_like_verbs_are_not_sentence_ends():
    from sukpago.text.clauses import ends_sentence
    for w in ("람다", "판다", "개요", "필요", "다", "아까"):
        assert not ends_sentence(w)
    for w in ("씁니다", "있다", "해요", "할까"):
        assert ends_sentence(w)



def test_take_head_does_not_take_a_lone_particle():
    c = ClauseCommitter()
    c.partial("에 맞추")
    c.partial("에 맞추어 작")
    assert c.take_head() is None  # '에' 다음 낱말이 아직 안정되지 않음
    c.partial("에 맞추어 작성")
    c.partial("에 맞추어 작성 중")
    assert c.take_head() == "에 맞추어"
    assert c.final("에 맞추어 작성 중입니다") == "작성 중입니다"


def test_protected_span_is_not_cut():
    c = ClauseCommitter(sentence_chars=5, clause_chars=5,
                        protect=lambda t: [(t.index("판다 스"), t.index("판다 스") + 4)] if "판다 스" in t else [])
    c.partial("분석할 때는 판다 스를 많이")
    assert c.partial("분석할 때는 판다 스를 많이 씁니다") == []  # '판다'에서 자르지 않음



def test_term_already_correct_is_not_cut_inside():
    from sukpago.text.glossary import Glossary, Rule
    g = Glossary([Rule("쿠다", "쿠다 툴킷")])
    c = ClauseCommitter(sentence_chars=5, clause_chars=5, protect=g.wrong_spans)
    c.partial("오늘 실습에서는 엔비디아 쿠다 툴킷을")
    assert c.partial("오늘 실습에서는 엔비디아 쿠다 툴킷을 설치해") == []
