"""MyMemory 온라인 번역. API 키가 필요 없다(이메일을 주면 하루 한도가 늘어남)."""

from __future__ import annotations

import html
import json
import urllib.error
import urllib.request
from typing import Callable
from urllib.parse import urlencode

from ..languages import SOURCE_MYMEMORY, get
from .base import QuotaExceeded, TranslateError

Fetch = Callable[[str, float], tuple[int, bytes]]
ENDPOINT = "https://api.mymemory.translated.net/get"


def _urllib_fetch(url: str, timeout: float) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": "SukPaGo/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise TranslateError(f"네트워크 오류: {e}") from e


class MyMemoryTranslator:
    name = "MyMemory"

    def __init__(self, email: str | None = None, timeout: float = 5.0,
                 fetch: Fetch | None = None) -> None:
        self.email = email
        self.timeout = timeout
        self._fetch = fetch or _urllib_fetch

    def translate(self, text: str, lang: str) -> str:
        params = {"q": text, "langpair": f"{SOURCE_MYMEMORY}|{get(lang).mymemory}"}
        if self.email:
            params["de"] = self.email
        status, body = self._fetch(f"{ENDPOINT}?{urlencode(params)}", self.timeout)
        if status == 429:
            raise QuotaExceeded("MyMemory 하루 한도를 넘었습니다")
        if status != 200:
            raise TranslateError(f"MyMemory HTTP {status}")
        try:
            data = json.loads(body)
        except ValueError as e:
            raise TranslateError("MyMemory 응답을 읽을 수 없습니다") from e
        if not isinstance(data, dict):
            raise TranslateError("MyMemory 응답 형식이 이상합니다")
        rd = data.get("responseData")
        out = rd.get("translatedText") if isinstance(rd, dict) else ""
        out = out if isinstance(out, str) else ""
        if data.get("quotaFinished") or "MYMEMORY WARNING" in out.upper():
            raise QuotaExceeded("MyMemory 하루 한도를 넘었습니다")
        try:
            code = int(data.get("responseStatus", 0))
        except (TypeError, ValueError):
            code = 0
        if code != 200:
            raise TranslateError(f"MyMemory 상태 {code}: {out}")
        out = html.unescape(out).strip()
        if not out:
            raise TranslateError("MyMemory가 빈 번역을 돌려주었습니다")
        return out
