# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec: single-file console executable. Built by scripts/build_exe.py
# (which sets RSA_EXE_NAME to e.g. rsa-0.1.0-windows-x64); `pyinstaller rsa.spec`
# on its own produces release/rsa[.exe].
import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# zoneinfo needs the IANA database; Windows has none, so bundle the tzdata package.
datas = collect_data_files("tzdata")
hiddenimports = collect_submodules("tzdata") + collect_submodules("rsa")

# `cryptography` is only used for optional Kalshi API-key signing (rsa/kalshi.py imports it lazily
# and the public market-data endpoints need no key). It is excluded from frozen builds by default:
# PyInstaller's cryptography hook imports the package during analysis and aborts the whole build
# when the installed copy is missing its Rust/cffi bindings. Set RSA_BUNDLE_CRYPTOGRAPHY=1 to
# include it (the build then requires a working `pip install cryptography`).
excludes = ["tkinter", "matplotlib", "scipy", "IPython", "pytest", "PIL"]
if os.environ.get("RSA_BUNDLE_CRYPTOGRAPHY") != "1":
    excludes.append("cryptography")

a = Analysis(
    ["scripts/launcher.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [("X utf8", None, "OPTION")],   # Python UTF-8 mode so console/file encoding is not the Windows code page
    name=os.environ.get("RSA_EXE_NAME", "rsa"),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
)
