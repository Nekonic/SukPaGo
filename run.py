"""석파고 한 줄 실행. 표준 라이브러리만 쓰므로 Python 3.10 이상이면 무엇으로 실행해도 된다.

    python run.py          # 환경·모델·고정 문장 음성을 준비하고 앱 실행
    python run.py setup    # 준비만 하고 실행은 안 함
"""

import sys

if sys.version_info < (3, 10):
    sys.stderr.write("Python 3.10 이상이 필요합니다. 지금 버전: %d.%d\n" % sys.version_info[:2])
    sys.exit(1)

import os  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import sysconfig  # noqa: E402
from pathlib import Path  # noqa: E402

ROOT = Path(__file__).resolve().parent
UV_EXE = "uv.exe" if sys.platform == "win32" else "uv"
ENSURE_CODE = "from sukpago.models import ensure; ensure('app')"
PHRASE_SCRIPT = "tools/build_phrase_audio.py"
UV_HELP = (
    "uv를 찾지 못했습니다. 아래 안내대로 설치한 뒤 다시 실행하세요.\n"
    "  Windows:  powershell -ExecutionPolicy ByPass -c \"irm https://astral.sh/uv/install.ps1 | iex\"\n"
    "  macOS/Linux:  curl -LsSf https://astral.sh/uv/install.sh | sh\n"
    "  자세한 내용: https://docs.astral.sh/uv/getting-started/installation/"
)


def _user_scripts_dir():
    """pip install --user가 실행 파일을 두는 폴더(Windows는 %APPDATA%\\Python\\PythonXY\\Scripts)."""
    scheme = "nt_user" if os.name == "nt" else "posix_user"
    try:
        return Path(sysconfig.get_path("scripts", scheme))
    except (KeyError, TypeError):
        return None


def find_uv():
    found = shutil.which("uv")
    if found:
        return found
    candidates = [Path.home() / ".local" / "bin" / UV_EXE]
    scripts = _user_scripts_dir()
    if scripts is not None:
        candidates.append(scripts / UV_EXE)
    for c in candidates:
        if c.is_file():
            return str(c)
    return None


def ensure_uv():
    uv = find_uv()
    if uv:
        return uv
    print("uv가 없어 pip로 설치합니다.", flush=True)
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "--user", "uv"], cwd=ROOT)
    except OSError:
        pass
    uv = find_uv()
    if not uv:
        print(UV_HELP, flush=True)
    return uv


def _run(cmd):
    return subprocess.run(cmd, cwd=ROOT).returncode


def main(argv=None):
    args = sys.argv[1:] if argv is None else list(argv)
    setup_only = bool(args) and args[0] == "setup"
    if args and not setup_only:
        print("사용: python run.py [setup]")
        return 2
    total = 3 if setup_only else 4

    def step(n, text):
        print("[%d/%d] %s" % (n, total, text), flush=True)

    step(1, "환경 준비")
    uv = ensure_uv()
    if not uv:
        return 1
    code = _run([uv, "sync", "--locked"])
    if code:
        print("환경 준비에 실패했습니다 (종료 코드 %d)." % code)
        return code

    step(2, "모델 준비")
    code = _run([uv, "run", "python", "-c", ENSURE_CODE])
    if code:
        print("모델 준비에 실패했습니다 (종료 코드 %d)." % code)
        return code

    step(3, "고정 문장 음성")
    if not (ROOT / PHRASE_SCRIPT).is_file():
        print("  경고: %s 가 없어 건너뜁니다." % PHRASE_SCRIPT)
    else:
        code = _run([uv, "run", "python", PHRASE_SCRIPT])
        if code:
            print("  경고: 고정 문장 음성을 만들지 못했습니다 (종료 코드 %d). 계속합니다." % code)

    if setup_only:
        print("준비가 끝났습니다. 실행: python run.py")
        return 0

    step(4, "실행")
    return _run([uv, "run", "python", "-m", "sukpago"])


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
