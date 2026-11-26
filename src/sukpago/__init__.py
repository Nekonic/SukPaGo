"""석파고(SukPaGo): 강의 실시간 번역기."""

import sys as _sys

# 콘솔·파이프 인코딩과 상관없이 출력은 항상 UTF-8로 한다(영문 Windows의 cp1252에서 한글 출력이 죽지 않게).
for _stream in (_sys.stdout, _sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # exe(창 모드)는 출력이 None
        pass
