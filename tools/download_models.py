"""models.lock.json에 적힌 모델을 받아 크기와 SHA256을 확인한다.

사용: uv run python tools/download_models.py [이름 ...] [--dest models]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

LOCK = Path(__file__).with_name("models.lock.json")
CHUNK = 1 << 20


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def is_valid(path: Path, sha256: str, size: int) -> bool:
    return path.is_file() and path.stat().st_size == size and sha256_file(path) == sha256


def _open(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "SukPaGo-model-downloader"})
    return urllib.request.urlopen(req, timeout=60)


def download(url: str, dest: Path, sha256: str, size: int, opener=_open) -> None:
    if is_valid(dest, sha256, size):
        print(f"  있음  {dest.name}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    h, n = hashlib.sha256(), 0
    with opener(url) as resp, open(part, "wb") as out:
        for block in iter(lambda: resp.read(CHUNK), b""):
            out.write(block)
            h.update(block)
            n += len(block)
    if n != size or h.hexdigest() != sha256:
        part.unlink(missing_ok=True)
        raise RuntimeError(f"{dest.name}: 크기 또는 SHA256 불일치 (받은 크기 {n}, 기대 {size})")
    part.replace(dest)
    print(f"  받음  {dest.name} ({n / 2**20:.0f}MB)")


def extract_stripped(archive: Path, dest: Path) -> None:
    """tar.bz2를 풀되 맨 위 폴더 하나를 벗긴다. 경로 탈출은 tarfile의 data 필터가 막는다."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=dest.parent) as tmp:
        with tarfile.open(archive, "r:bz2") as tf:
            tf.extractall(tmp, filter="data")
        roots = list(Path(tmp).iterdir())
        src = roots[0] if len(roots) == 1 and roots[0].is_dir() else Path(tmp)
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True)
        for child in src.iterdir():
            shutil.move(str(child), dest / child.name)


def fetch_model(name: str, spec: dict, root: Path, opener=_open) -> None:
    print(f"[{name}]")
    target = root / spec["dir"]
    for f in spec.get("files", []):
        download(f["url"], target / f["name"], f["sha256"], f["size"], opener)
    archive = spec.get("archive")
    if archive:
        stamp = target / ".archive-sha256"
        if stamp.is_file() and stamp.read_text().strip() == archive["sha256"]:
            print("  있음  (압축 해제됨)")
            return
        tmp = root / f".{name}.tar.bz2"
        download(archive["url"], tmp, archive["sha256"], archive["size"], opener)
        extract_stripped(tmp, target)
        tmp.unlink()
        stamp.write_text(archive["sha256"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="석파고 모델 받기")
    parser.add_argument("names", nargs="*", help="받을 모델 이름 (생략하면 전부)")
    parser.add_argument("--dest", type=Path, default=Path(__file__).resolve().parents[1] / "models")
    args = parser.parse_args(argv)
    lock = json.loads(LOCK.read_text("utf-8"))["models"]
    names = args.names or list(lock)
    unknown = [n for n in names if n not in lock]
    if unknown:
        print(f"모르는 모델: {unknown}. 가능한 이름: {list(lock)}", file=sys.stderr)
        return 2
    for name in names:
        fetch_model(name, lock[name], args.dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
