import hashlib
import io
import json
import os
import tarfile

import pytest

from sukpago import models


def blob(data):
    return hashlib.sha256(data).hexdigest(), len(data)


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def make_tar_bytes(members):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:bz2") as tf:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


# ---- 검증 기록 ----------------------------------------------------------


def count_hashes(monkeypatch):
    calls = []
    real = models.sha256_file

    def fake(path):
        calls.append(path)
        return real(path)

    monkeypatch.setattr(models, "sha256_file", fake)
    return calls


def test_is_valid_writes_stamp_and_skips_hash_next_time(tmp_path, monkeypatch):
    f = tmp_path / "f.bin"
    f.write_bytes(b"hello")
    sha, size = blob(b"hello")
    calls = count_hashes(monkeypatch)

    assert models.is_valid(f, sha, size)
    assert len(calls) == 1
    stamp = json.loads((tmp_path / "f.bin.verified").read_text("utf-8"))
    assert stamp == {"size": size, "mtime_ns": f.stat().st_mtime_ns, "sha256": sha}

    assert models.is_valid(f, sha, size)
    assert len(calls) == 1


def test_is_valid_rehashes_after_file_changes(tmp_path, monkeypatch):
    f = tmp_path / "f.bin"
    f.write_bytes(b"hello")
    sha, size = blob(b"hello")
    assert models.is_valid(f, sha, size)

    calls = count_hashes(monkeypatch)
    f.write_bytes(b"jello")  # 크기는 같고 내용만 다름
    st = f.stat()
    os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
    assert not models.is_valid(f, sha, size)
    assert len(calls) == 1
    assert not (tmp_path / "f.bin.verified").exists()


def test_is_valid_ignores_stamp_for_other_hash(tmp_path, monkeypatch):
    f = tmp_path / "f.bin"
    f.write_bytes(b"hello")
    sha, size = blob(b"hello")
    assert models.is_valid(f, sha, size)
    calls = count_hashes(monkeypatch)
    assert not models.is_valid(f, "0" * 64, size)
    assert len(calls) == 1


def test_is_valid_missing_or_wrong_size(tmp_path):
    f = tmp_path / "f.bin"
    assert not models.is_valid(f, "0" * 64, 5)
    f.write_bytes(b"hi")
    assert not models.is_valid(f, "0" * 64, 5)


def test_download_writes_stamp_without_rehash(tmp_path, monkeypatch):
    data = b"payload"
    sha, size = blob(data)
    dest = tmp_path / "m" / "f.bin"
    models.download("u", dest, sha, size, lambda url: FakeResp(data))
    calls = count_hashes(monkeypatch)
    assert models.is_valid(dest, sha, size)
    assert calls == []


def test_download_reports_progress(tmp_path, monkeypatch):
    monkeypatch.setattr(models, "CHUNK", 4)
    data = b"0123456789"
    sha, size = blob(data)
    seen = []
    models.download("u", tmp_path / "f.bin", sha, size, lambda url: FakeResp(data),
                    progress=lambda name, done, total: seen.append((name, done, total)))
    assert seen[0] == ("f.bin", 0, 10)
    assert seen[-1] == ("f.bin", 10, 10)
    assert [d for _, d, _ in seen] == sorted(d for _, d, _ in seen)


# ---- ensure ------------------------------------------------------------


@pytest.fixture
def fake_lock(tmp_path, monkeypatch):
    a, b, c = b"aaa", b"bbbb", b"ccccc"
    arc = make_tar_bytes({"top/model.onnx": b"m", "top/tokens.txt": b"t"})
    content = {"u/a": a, "u/b": b, "u/c": c, "u/arc": arc}

    def spec(name, data, url):
        sha, size = blob(data)
        return {"name": name, "size": size, "sha256": sha, "url": url}

    lock = {
        "models": {
            "one": {"dir": "one", "files": [spec("a.bin", a, "u/a"), spec("b.bin", b, "u/b")]},
            "arch": {"dir": "arch", "archive": {k: v for k, v in spec("x", arc, "u/arc").items()
                                                 if k != "name"}},
            "big": {"dir": "big", "files": [spec("c.bin", c, "u/c")]},
        },
        "roles": {"app": ["one", "arch"], "eval": ["big"]},
    }
    lock_file = tmp_path / "models.lock.json"
    lock_file.write_text(json.dumps(lock), "utf-8")
    root = tmp_path / "models"
    calls = []

    def opener(url):
        calls.append(url)
        return FakeResp(content[url])

    monkeypatch.setattr(models, "lock_path", lambda: lock_file)
    monkeypatch.setattr(models, "_open", opener)
    monkeypatch.setenv("SUKPAGO_MODELS", str(root))
    return root, calls, content


def test_ensure_app_fetches_only_app_role_and_missing_files(fake_lock):
    root, calls, content = fake_lock
    (root / "one").mkdir(parents=True)
    (root / "one" / "a.bin").write_bytes(content["u/a"])

    seen = []
    new = models.ensure("app", progress=lambda n, d, t: seen.append((n, d, t)))

    assert sorted(calls) == ["u/arc", "u/b"]
    assert sorted(new) == ["arch.tar.bz2", "b.bin"]
    assert (root / "one" / "b.bin").read_bytes() == content["u/b"]
    assert (root / "arch" / "model.onnx").read_bytes() == b"m"
    assert not (root / "big").exists()
    names = {n for n, _, _ in seen}
    assert names == {"b.bin", "arch.tar.bz2"}
    assert ("b.bin", 4, 4) in seen


def test_ensure_second_call_downloads_nothing(fake_lock, monkeypatch):
    root, calls, _ = fake_lock
    models.ensure()
    calls.clear()
    hashes = count_hashes(monkeypatch)
    assert models.ensure("app") == []
    assert calls == []
    assert hashes == []


def test_ensure_eval_role(fake_lock):
    root, calls, _ = fake_lock
    assert models.ensure("eval") == ["c.bin"]
    assert calls == ["u/c"]


def test_ensure_unknown_role_is_keyerror(fake_lock):
    with pytest.raises(KeyError):
        models.ensure("nope")


# ---- 잠금 파일 ------------------------------------------------------------


def test_real_lock_roles_cover_all_models():
    lock = json.loads(models.lock_path().read_text("utf-8"))
    roles = lock["roles"]
    assert roles["app"] == ["zipformer-ko", "nllb-600m"]
    assert set(roles["app"]).isdisjoint(roles["eval"])
    assert set(roles["app"]) | set(roles["eval"]) == set(lock["models"])


def test_lock_path_frozen_looks_next_to_exe(tmp_path, monkeypatch):
    exe_dir = tmp_path / "dist"
    (exe_dir / "tools").mkdir(parents=True)
    (exe_dir / "tools" / "models.lock.json").write_text("{}", "utf-8")
    monkeypatch.setattr(models.sys, "frozen", True, raising=False)
    monkeypatch.setattr(models.sys, "executable", str(exe_dir / "SukPaGo.exe"))
    assert models.lock_path() == exe_dir / "tools" / "models.lock.json"


def test_lock_path_frozen_falls_back_to_package_data(tmp_path, monkeypatch):
    monkeypatch.setattr(models.sys, "frozen", True, raising=False)
    monkeypatch.setattr(models.sys, "executable", str(tmp_path / "SukPaGo.exe"))
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "models.lock.json").write_text("{}", "utf-8")
    monkeypatch.setattr(models, "_PACKAGE_LOCK", pkg / "models.lock.json")
    assert models.lock_path() == pkg / "models.lock.json"
