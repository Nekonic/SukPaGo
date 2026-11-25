"""models.lock.json에 적힌 모델을 받아 크기와 SHA256을 확인한다.

사용: uv run python tools/download_models.py [이름 ...] [--role app|eval] [--dest models]
실제 동작은 sukpago.models에 있다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sukpago.models import (  # noqa: F401  (다시 내보냄)
    CHUNK,
    _open,
    download,
    extract_stripped,
    fetch_model,
    is_valid,
    sha256_file,
)

LOCK = Path(__file__).with_name("models.lock.json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="석파고 모델 받기")
    parser.add_argument("names", nargs="*", help="받을 모델 이름 (생략하면 전부)")
    parser.add_argument("--role", help="roles에 적힌 묶음 이름 (app, eval)")
    parser.add_argument("--dest", type=Path, default=Path(__file__).resolve().parents[1] / "models")
    args = parser.parse_args(argv)
    data = json.loads(LOCK.read_text("utf-8"))
    lock, roles = data["models"], data.get("roles", {})
    if args.role and args.role not in roles:
        print(f"모르는 role: {args.role}. 가능한 이름: {list(roles)}", file=sys.stderr)
        return 2
    names = args.names or (roles[args.role] if args.role else list(lock))
    unknown = [n for n in names if n not in lock]
    if unknown:
        print(f"모르는 모델: {unknown}. 가능한 이름: {list(lock)}", file=sys.stderr)
        return 2
    for name in names:
        fetch_model(name, lock[name], args.dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
