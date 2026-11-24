import hashlib
import io
import json
import tarfile

import pytest

import download_models as dm


def blob(data):
    return hashlib.sha256(data).hexdigest(), len(data)


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def opener_for(data, calls):
    def op(url):
        calls.append(url)
        return FakeResp(data)

    return op


def test_download_verifies_and_skips_existing(tmp_path):
    data, calls = b"hello", []
    sha, size = blob(data)
    dest = tmp_path / "m" / "f.bin"
    dm.download("u", dest, sha, size, opener_for(data, calls))
    assert dest.read_bytes() == data
    dm.download("u", dest, sha, size, opener_for(data, calls))
    assert calls == ["u"]


def test_download_rejects_bad_hash(tmp_path):
    sha, size = blob(b"good")
    dest = tmp_path / "f.bin"
    with pytest.raises(RuntimeError, match="불일치"):
        dm.download("u", dest, sha, size, opener_for(b"evil", []))
    assert not dest.exists()
    assert not (tmp_path / "f.bin.part").exists()


def make_tar(path, members):
    with tarfile.open(path, "w:bz2") as tf:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))


def test_extract_strips_top_folder(tmp_path):
    arc = tmp_path / "a.tar.bz2"
    make_tar(arc, {"top/model.onnx": b"m", "top/sub/x.wav": b"w"})
    dest = tmp_path / "out"
    dm.extract_stripped(arc, dest)
    assert (dest / "model.onnx").read_bytes() == b"m"
    assert (dest / "sub" / "x.wav").exists()


def test_extract_blocks_path_traversal(tmp_path):
    arc = tmp_path / "a.tar.bz2"
    make_tar(arc, {"../evil.txt": b"x"})
    with pytest.raises(tarfile.FilterError):
        dm.extract_stripped(arc, tmp_path / "out")
    assert not (tmp_path.parent / "evil.txt").exists()


def test_lock_file_is_complete():
    lock = json.loads(dm.LOCK.read_text("utf-8"))["models"]
    assert set(lock) == {"nllb-600m", "hymt2-q4", "zipformer-ko", "sensevoice-ko", "silero-vad",
                         "nllb-1.3b", "tsengel-1.3b", "tgemma-q4", "qwen3-asr"}
    for spec in lock.values():
        entries = spec.get("files", []) + ([spec["archive"]] if "archive" in spec else [])
        assert entries
        for e in entries:
            assert len(e["sha256"]) == 64 and e["size"] > 0
            assert e["url"].startswith("https://")
            assert "/resolve/main/" not in e["url"]
