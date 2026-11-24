import sys

from sukpago import paths


def test_dev_root_is_repo_root():
    assert (paths.app_root() / "pyproject.toml").exists()


def test_frozen_root_is_exe_folder(monkeypatch, tmp_path):
    monkeypatch.delenv("SUKPAGO_MODELS", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "SukPaGo.exe"))
    assert paths.app_root() == tmp_path.resolve()
    assert paths.models_dir() == tmp_path.resolve() / "models"
    assert paths.assets_dir() == tmp_path.resolve() / "assets"


def test_models_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("SUKPAGO_MODELS", str(tmp_path))
    assert paths.models_dir() == tmp_path
