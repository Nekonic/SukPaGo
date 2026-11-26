import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def run_mod():
    spec = importlib.util.spec_from_file_location("sukpago_run", ROOT / "run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Recorder:
    def __init__(self, codes=None):
        self.cmds = []
        self.codes = codes or {}

    def __call__(self, cmd, **kw):
        self.cmds.append(list(cmd))
        assert not kw.get("shell")
        code = 0
        for key, c in self.codes.items():
            if key in " ".join(cmd):
                code = c
        return subprocess.CompletedProcess(cmd, code)


UV = "/fake/uv"


def expected(app=True):
    cmds = [
        [UV, "sync", "--locked"],
        [UV, "run", "python", "-c", "from sukpago.models import ensure; ensure('app')"],
        [UV, "run", "python", "tools/build_phrase_audio.py"],
    ]
    if app:
        cmds.append([UV, "run", "python", "-m", "sukpago"])
    return cmds


@pytest.fixture
def phrase_script(run_mod, tmp_path, monkeypatch):
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "build_phrase_audio.py").write_text("", "utf-8")
    monkeypatch.setattr(run_mod, "ROOT", tmp_path)
    return tmp_path


def test_default_runs_all_steps_then_app(run_mod, phrase_script, monkeypatch, capsys):
    rec = Recorder({"-m sukpago": 3})
    monkeypatch.setattr(run_mod.shutil, "which", lambda name: UV)
    monkeypatch.setattr(run_mod.subprocess, "run", rec)
    assert run_mod.main([]) == 3
    assert rec.cmds == expected(app=True)
    out = capsys.readouterr().out
    assert "[1/4]" in out and "[4/4]" in out


def test_setup_skips_app(run_mod, phrase_script, monkeypatch):
    rec = Recorder()
    monkeypatch.setattr(run_mod.shutil, "which", lambda name: UV)
    monkeypatch.setattr(run_mod.subprocess, "run", rec)
    assert run_mod.main(["setup"]) == 0
    assert rec.cmds == expected(app=False)


def test_commands_run_from_repo_root(run_mod, phrase_script, monkeypatch):
    cwds = []

    def fake(cmd, **kw):
        cwds.append(kw.get("cwd"))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(run_mod.shutil, "which", lambda name: UV)
    monkeypatch.setattr(run_mod.subprocess, "run", fake)
    run_mod.main(["setup"])
    assert cwds and all(Path(c) == phrase_script for c in cwds)


@pytest.mark.parametrize("failing, code, ran", [("sync", 5, 1), ("ensure", 7, 2)])
def test_failure_stops_with_code(run_mod, phrase_script, monkeypatch, failing, code, ran):
    rec = Recorder({failing: code})
    monkeypatch.setattr(run_mod.shutil, "which", lambda name: UV)
    monkeypatch.setattr(run_mod.subprocess, "run", rec)
    assert run_mod.main([]) == code
    assert rec.cmds == expected()[:ran]


def test_phrase_audio_failure_only_warns(run_mod, phrase_script, monkeypatch, capsys):
    rec = Recorder({"build_phrase_audio": 1})
    monkeypatch.setattr(run_mod.shutil, "which", lambda name: UV)
    monkeypatch.setattr(run_mod.subprocess, "run", rec)
    assert run_mod.main([]) == 0
    assert rec.cmds == expected()


def test_missing_phrase_script_warns_and_continues(run_mod, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(run_mod, "ROOT", tmp_path)
    rec = Recorder()
    monkeypatch.setattr(run_mod.shutil, "which", lambda name: UV)
    monkeypatch.setattr(run_mod.subprocess, "run", rec)
    assert run_mod.main([]) == 0
    assert rec.cmds == [c for c in expected() if "tools/build_phrase_audio.py" not in c]
    assert "build_phrase_audio.py" in capsys.readouterr().out


def test_find_uv_falls_back_to_local_bin(run_mod, tmp_path, monkeypatch):
    monkeypatch.setattr(run_mod.shutil, "which", lambda name: None)
    monkeypatch.setattr(run_mod.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(run_mod, "_user_scripts_dir", lambda: None)
    assert run_mod.find_uv() is None
    exe = "uv.exe" if sys.platform == "win32" else "uv"
    (tmp_path / ".local" / "bin").mkdir(parents=True)
    (tmp_path / ".local" / "bin" / exe).write_text("", "utf-8")
    assert run_mod.find_uv() == str(tmp_path / ".local" / "bin" / exe)


def test_missing_uv_tries_pip_install(run_mod, phrase_script, monkeypatch):
    state = {"installed": False}
    cmds = []

    def fake(cmd, **kw):
        cmds.append(list(cmd))
        if cmd[1:4] == ["-m", "pip", "install"]:
            state["installed"] = True
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(run_mod, "find_uv", lambda: UV if state["installed"] else None)
    monkeypatch.setattr(run_mod.subprocess, "run", fake)
    assert run_mod.main(["setup"]) == 0
    assert cmds[0] == [sys.executable, "-m", "pip", "install", "--user", "uv"]
    assert cmds[1:] == expected(app=False)


def test_uv_still_missing_exits_1(run_mod, phrase_script, monkeypatch, capsys):
    cmds = []

    def fake(cmd, **kw):
        cmds.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 1)

    monkeypatch.setattr(run_mod, "find_uv", lambda: None)
    monkeypatch.setattr(run_mod.subprocess, "run", fake)
    assert run_mod.main([]) == 1
    assert cmds == [[sys.executable, "-m", "pip", "install", "--user", "uv"]]
    assert "uv" in capsys.readouterr().out


def test_run_py_uses_only_stdlib():
    import ast

    tree = ast.parse((ROOT / "run.py").read_text("utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    assert names <= set(sys.stdlib_module_names) | {"__future__"}


def test_korean_output_survives_non_utf8_console(tmp_path):
    env = {"PATH": "", "PYTHONIOENCODING": "cp1252", "SYSTEMROOT": "C:\\Windows"}
    r = subprocess.run([sys.executable, str(ROOT / "run.py"), "bogus"], capture_output=True, env=env)
    assert r.returncode == 2
    assert "사용: python run.py" in r.stdout.decode("utf-8")


def test_child_processes_get_utf8_env(run_mod, monkeypatch):
    seen = {}

    def fake_run(cmd, **kw):
        seen.update(kw.get("env") or {})
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(run_mod.subprocess, "run", fake_run)
    run_mod._run(["x"])
    assert seen.get("PYTHONUTF8") == "1"


def test_package_import_forces_utf8_output():
    env = {"PATH": "", "PYTHONIOENCODING": "cp1252", "SYSTEMROOT": "C:\\Windows",
           "PYTHONPATH": str(ROOT / "src")}
    r = subprocess.run([sys.executable, "-c", "import sukpago; print('한글 출력')"],
                       capture_output=True, env=env)
    assert r.returncode == 0, r.stderr
    assert r.stdout.decode("utf-8").strip() == "한글 출력"
