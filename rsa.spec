# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Robinhood Soccer HQ. One analysis, two single-file executables:
#   * the windowed app (RobinhoodSoccerHQ[.exe]; on macOS also "Robinhood Soccer HQ.app")
#   * the console CLI (rsa[.exe])
# Built by scripts/build_exe.py (which sets RSA_GUI_NAME / RSA_CLI_NAME and --distpath release/);
# `pyinstaller rsa.spec` on its own writes dist/RobinhoodSoccerHQ[.exe] and dist/rsa[.exe].
import os
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# zoneinfo needs the IANA database; Windows has none, so bundle the tzdata package.
datas = collect_data_files("tzdata")
# the HQ web UI (html/css/js/svg) travels with the package
datas += [(os.path.join(SPECPATH, "rsa", "hq", "ui"), os.path.join("rsa", "hq", "ui"))]
hiddenimports = collect_submodules("tzdata") + collect_submodules("rsa")

# `cryptography` is only used for optional Kalshi API-key signing (rsa/kalshi.py imports it lazily
# and the public market-data endpoints need no key). It is excluded from frozen builds by default:
# PyInstaller's cryptography hook imports the package during analysis and aborts the whole build
# when the installed copy is missing its Rust/cffi bindings. Set RSA_BUNDLE_CRYPTOGRAPHY=1 to
# include it (the build then requires a working `pip install cryptography`).
excludes = ["tkinter", "matplotlib", "scipy", "IPython", "pytest", "PIL"]
if os.environ.get("RSA_BUNDLE_CRYPTOGRAPHY") != "1":
    excludes.append("cryptography")

# SPECPATH is the directory holding this spec file, so the build works from any cwd.
a = Analysis(
    [os.path.join(SPECPATH, "scripts", "launcher.py")],
    pathex=[SPECPATH],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)
RUNTIME_OPTIONS = [("X utf8", None, "OPTION")]   # Python UTF-8 mode so console/file encoding is not the Windows code page
ICON = os.environ.get("RSA_ICON") or None          # build/icon/icon.ico or icon.icns from scripts/make_icon.py

cli = EXE(
    pyz, a.scripts, a.binaries, a.datas, RUNTIME_OPTIONS,
    name=os.environ.get("RSA_CLI_NAME", "rsa"),
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=True, disable_windowed_traceback=False,
)
gui = EXE(
    pyz, a.scripts, a.binaries, a.datas, RUNTIME_OPTIONS,
    name=os.environ.get("RSA_GUI_NAME", "RobinhoodSoccerHQ"),
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False, disable_windowed_traceback=False,
    icon=ICON if sys.platform in ("win32", "darwin") else None,
)
if sys.platform == "darwin":
    app = BUNDLE(
        gui,
        name="Robinhood Soccer HQ.app",
        icon=ICON,
        bundle_identifier="com.alomarif.robinhoodsoccerhq",
        info_plist={"CFBundleDisplayName": "Robinhood Soccer HQ", "CFBundleShortVersionString": os.environ.get("RSA_VERSION", "0.0.0"),
                    "NSHighResolutionCapable": True, "LSMinimumSystemVersion": "12.0"},
    )
