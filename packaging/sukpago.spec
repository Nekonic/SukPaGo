# -*- mode: python ; coding: utf-8 -*-
# PyInstaller onedir 빌드: uv run pyinstaller --noconfirm --clean packaging/sukpago.spec
# models/, assets/, tools/models.lock.json은 빌드 뒤 release.yml이 dist/SukPaGo/에 복사한다.
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

ROOT = Path(SPECPATH).resolve().parent

datas = collect_data_files("customtkinter") + collect_data_files("sherpa_onnx")
binaries = collect_dynamic_libs("sherpa_onnx") + collect_dynamic_libs("ctranslate2")
hiddenimports = (
    collect_submodules("sukpago")
    + ["sherpa_onnx", "ctranslate2", "sentencepiece", "edge_tts", "miniaudio", "_cffi_backend", "psutil"]
)

a = Analysis(
    [str(ROOT / "packaging" / "launch.py")],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["pytest", "llama_cpp"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SukPaGo",
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="SukPaGo")
