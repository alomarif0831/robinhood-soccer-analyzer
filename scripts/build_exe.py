"""Build the Robinhood Soccer HQ executables with PyInstaller.

Outputs in release/: RobinhoodSoccerHQ-<version>-<os>-<arch>[.exe] (the windowed app),
rsa-<version>-<os>-<arch>[.exe] (the console CLI), plain-named copies of both, and on
macOS "Robinhood Soccer HQ.app". Run `python scripts/build_exe.py` from any directory;
needs `pip install -e .[build]`.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def target_suffix(version: str) -> str:
    os_name = {"Windows": "windows", "Darwin": "macos", "Linux": "linux"}.get(platform.system(), platform.system().lower())
    arch = platform.machine().lower()
    arch = {"amd64": "x64", "x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(arch, arch)
    return f"{version}-{os_name}-{arch}"


def target_name(version: str) -> str:
    return f"rsa-{target_suffix(version)}"


def main() -> int:
    sys.path.insert(0, str(ROOT))
    from rsa import __version__

    tag = target_suffix(__version__)
    cli_name, gui_name = f"rsa-{tag}", f"RobinhoodSoccerHQ-{tag}"
    suffix = ".exe" if platform.system() == "Windows" else ""
    release = ROOT / "release"
    release.mkdir(exist_ok=True)
    env = dict(os.environ, RSA_CLI_NAME=cli_name, RSA_GUI_NAME=gui_name, RSA_VERSION=__version__)
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
           "--distpath", str(release), "--workpath", str(ROOT / "build" / "pyinstaller"), str(ROOT / "rsa.spec")]
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=ROOT, env=env)

    cli = release / f"{cli_name}{suffix}"
    gui = release / f"{gui_name}{suffix}"
    for exe in (cli, gui):
        if not exe.exists():
            print(f"error: expected {exe} after the build", file=sys.stderr)
            return 1
    shutil.copy2(cli, release / f"rsa{suffix}")
    shutil.copy2(gui, release / f"RobinhoodSoccerHQ{suffix}")
    out = subprocess.run([str(cli), "--version"], capture_output=True, text=True, check=True).stdout.strip()
    smoke = subprocess.run([str(gui), "hq", "--smoke"], capture_output=True, text=True)
    print(f"\nBuilt {cli} ({cli.stat().st_size / 1e6:.1f} MB), reports version {out}")
    print(f"Built {gui} ({gui.stat().st_size / 1e6:.1f} MB); `hq --smoke` exit code {smoke.returncode}")
    if smoke.returncode != 0:
        print(smoke.stdout[-2000:], smoke.stderr[-2000:], file=sys.stderr)
        return 1
    if platform.system() == "Darwin" and (release / "Robinhood Soccer HQ.app").exists():
        print("Built release/Robinhood Soccer HQ.app")
    return 0


if __name__ == "__main__":
    sys.exit(main())
