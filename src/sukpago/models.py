"""models.lock.json에 적힌 모델을 받아 크기와 SHA256을 확인하고 models_dir()에 둔다.

검증을 통과한 파일 옆에는 `<파일>.verified`(크기, 수정 시각, SHA256)를 남긴다.
기록이 실제 파일과 맞으면 다음부터 해시 계산을 건너뛴다.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from collections.abc import Callable
from pathlib import Path

from sukpago import paths

CHUNK = 1 << 20
STAMP_SUFFIX = ".verified"
_PACKAGE_LOCK = Path(__file__).with_name("models.lock.json")

Progress = Callable[[str, int, int], None]


def lock_path() -> Path:
    """잠금 파일 위치. 개발 중에는 저장소의 tools/, exe에서는 exe 옆 tools/, 없으면 패키지 안."""
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path(__file__).resolve().parents[2]
    candidate = base / "tools" / "models.lock.json"
    if candidate.is_file() or not _PACKAGE_LOCK.is_file():
        return candidate
    return _PACKAGE_LOCK


def load_lock() -> dict:
    return json.loads(lock_path().read_text("utf-8"))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def _stamp_path(path: Path) -> Path:
    return path.with_name(path.name + STAMP_SUFFIX)


def _write_stamp(path: Path, sha256: str) -> None:
    st = path.stat()
    record = {"size": st.st_size, "mtime_ns": st.st_mtime_ns, "sha256": sha256}
    try:
        _stamp_path(path).write_text(json.dumps(record), "utf-8")
    except OSError:
        pass  # 읽기 전용 폴더: 기록이 없으면 다음에 해시를 다시 계산할 뿐이다


def _stamp_matches(path: Path, sha256: str, st) -> bool:
    try:
        record = json.loads(_stamp_path(path).read_text("utf-8"))
    except (OSError, ValueError):
        return False
    return (isinstance(record, dict) and record.get("size") == st.st_size
            and record.get("mtime_ns") == st.st_mtime_ns and record.get("sha256") == sha256)


def is_valid(path: Path, sha256: str, size: int) -> bool:
    if not path.is_file():
        return False
    st = path.stat()
    if st.st_size != size:
        return False
    if _stamp_matches(path, sha256, st):
        return True
    if sha256_file(path) == sha256:
        _write_stamp(path, sha256)
        return True
    _stamp_path(path).unlink(missing_ok=True)
    return False


def _open(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "SukPaGo-model-downloader"})
    return urllib.request.urlopen(req, timeout=60)


def download(url: str, dest: Path, sha256: str, size: int, opener=None,
             progress: Progress | None = None) -> bool:
    """dest가 이미 맞으면 False, 새로 받았으면 True. 크기나 해시가 다르면 RuntimeError."""
    if is_valid(dest, sha256, size):
        print(f"  있음  {dest.name}")
        return False
    opener = opener or _open
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    h, n = hashlib.sha256(), 0
    if progress:
        progress(dest.name, 0, size)
    try:
        with opener(url) as resp, open(part, "wb") as out:
            for block in iter(lambda: resp.read(CHUNK), b""):
                out.write(block)
                h.update(block)
                n += len(block)
                if progress:
                    progress(dest.name, n, size)
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    if n != size or h.hexdigest() != sha256:
        part.unlink(missing_ok=True)
        raise RuntimeError(f"{dest.name}: 크기 또는 SHA256 불일치 (받은 크기 {n}, 기대 {size})")
    part.replace(dest)
    _write_stamp(dest, sha256)
    print(f"  받음  {dest.name} ({n / 2**20:.0f}MB)")
    return True


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


def fetch_model(name: str, spec: dict, root: Path, opener=None,
                progress: Progress | None = None) -> list[str]:
    """모델 하나를 root/spec['dir']에 준비하고 새로 받은 파일 이름 목록을 돌려준다."""
    print(f"[{name}]")
    target = root / spec["dir"]
    new: list[str] = []
    for f in spec.get("files", []):
        if download(f["url"], target / f["name"], f["sha256"], f["size"], opener, progress):
            new.append(f["name"])
    archive = spec.get("archive")
    if archive:
        stamp = target / ".archive-sha256"
        if stamp.is_file() and stamp.read_text().strip() == archive["sha256"]:
            print("  있음  (압축 해제됨)")
            return new
        tmp = root / f"{name}.tar.bz2"
        if download(archive["url"], tmp, archive["sha256"], archive["size"], opener, progress):
            new.append(tmp.name)
        extract_stripped(tmp, target)
        tmp.unlink()
        _stamp_path(tmp).unlink(missing_ok=True)
        stamp.write_text(archive["sha256"])
    return new


def ensure(role: str = "app", *, progress: Progress | None = None) -> list[str]:
    """roles[role]의 모델을 models_dir()에 준비하고 새로 받은 파일 이름 목록을 돌려준다.

    모르는 role이면 KeyError. progress(파일이름, 받은 바이트, 전체 바이트).
    """
    lock = load_lock()
    names = lock["roles"][role]
    root = paths.models_dir()
    new: list[str] = []
    for name in names:
        new += fetch_model(name, lock["models"][name], root, _open, progress)
    return new
