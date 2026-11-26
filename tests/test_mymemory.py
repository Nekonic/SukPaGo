import json
from urllib.parse import parse_qs, urlparse

import pytest

from sukpago.translate.base import QuotaExceeded, TranslateError
from sukpago.translate.mymemory import MyMemoryTranslator

OK = {"responseStatus": 200, "quotaFinished": False,
      "responseData": {"translatedText": "Анхаарлаа төвлөрүүл."}}


def fake(status=200, payload=None, raw=None):
    calls = []

    def fetch(url, timeout):
        calls.append((url, timeout))
        return status, (raw if raw is not None else json.dumps(payload).encode())

    return fetch, calls


def query(calls):
    return parse_qs(urlparse(calls[0][0]).query)


def test_builds_query_and_parses():
    fetch, calls = fake(payload=OK)
    assert MyMemoryTranslator(fetch=fetch).translate("집중하세요.", "mn") == "Анхаарлаа төвлөрүүл."
    q = query(calls)
    assert q["q"] == ["집중하세요."] and q["langpair"] == ["ko|mn"] and "de" not in q
    assert calls[0][1] == 5.0


def test_email_and_chinese_code():
    fetch, calls = fake(payload=OK)
    MyMemoryTranslator(email="me@example.com", fetch=fetch).translate("x", "zh")
    q = query(calls)
    assert q["langpair"] == ["ko|zh-CN"] and q["de"] == ["me@example.com"]


def test_html_entities_unescaped():
    fetch, _ = fake(payload={**OK, "responseData": {"translatedText": "let&#39;s go"}})
    assert MyMemoryTranslator(fetch=fetch).translate("x", "en") == "let's go"


@pytest.mark.parametrize("status,payload", [
    (200, {**OK, "quotaFinished": True}),
    (200, {"responseStatus": 429, "responseData": {
        "translatedText": "MYMEMORY WARNING: YOU USED ALL AVAILABLE FREE TRANSLATIONS FOR TODAY."}}),
    (429, {}),
])
def test_quota(status, payload):
    fetch, _ = fake(status=status, payload=payload)
    with pytest.raises(QuotaExceeded):
        MyMemoryTranslator(fetch=fetch).translate("x", "en")


@pytest.mark.parametrize("status,raw", [
    (500, b"oops"),
    (200, b"not json"),
    (200, json.dumps({"responseStatus": "403",
                      "responseData": {"translatedText": "INVALID LANGUAGE PAIR"}}).encode()),
    (200, json.dumps({"responseStatus": 200, "responseData": {"translatedText": "  "}}).encode()),
])
def test_errors(status, raw):
    fetch, _ = fake(status=status, raw=raw)
    with pytest.raises(TranslateError) as e:
        MyMemoryTranslator(fetch=fetch).translate("x", "en")
    assert not isinstance(e.value, QuotaExceeded)


@pytest.mark.parametrize("raw", [b"null", b"[]", b'"text"', json.dumps({"responseStatus": 200, "responseData": "x"}).encode()])
def test_non_object_json_is_translate_error(raw):
    fetch, _ = fake(raw=raw)
    with pytest.raises(TranslateError):
        MyMemoryTranslator(fetch=fetch).translate("x", "en")
