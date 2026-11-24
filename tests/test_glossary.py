import pytest

from sukpago.text.glossary import Glossary, Rule


def test_replaces_regardless_of_spacing():
    g = Glossary([Rule("노트북 에램", "NotebookLM")])
    assert g.apply("노트북에램 써 보셨나요") == "NotebookLM 써 보셨나요"
    assert g.apply("노트북  에램 이라는") == "NotebookLM 이라는"


def test_longest_rule_wins():
    g = Glossary([Rule("노트북", "랩톱"), Rule("노트북 에램", "NotebookLM")])
    assert g.apply("노트북 에램과 노트북") == "NotebookLM과 랩톱"


def test_add_replaces_same_wrong_and_remove():
    g = Glossary()
    g.add("한강 리스크", "할루시네이션")
    g.add("한강 리스크", "할루시네이션 리스크")
    assert g.rules == [Rule("한강 리스크", "할루시네이션 리스크")]
    g.remove("한강 리스크")
    assert g.apply("한강 리스크") == "한강 리스크"


def test_empty_rule_rejected():
    with pytest.raises(ValueError):
        Glossary().add(" ", "x")


def test_special_characters_are_literal():
    g = Glossary([Rule("C++", "씨플플")])
    assert g.apply("C++ 수업") == "씨플플 수업"


def test_json_roundtrip():
    g = Glossary([Rule("a b", "AB")])
    assert Glossary.from_json(g.to_json()).rules == g.rules
