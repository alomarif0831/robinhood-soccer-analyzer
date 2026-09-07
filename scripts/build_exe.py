"""Build a single-file executable with PyInstaller.

Output: release/rsa-<version>-<os>-<arch>[.exe] plus a plain release/rsa[.exe] copy.
Run `python scripts/build_exe.py` from any directory; needs `pip install -e .[build]`.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def target_name(version: str) -> str:
    os_name = {"Windows": "windows", "Darwin": "macos", "Linux": "linux"}.get(platform.system(), platform.system().lower())
    arch = platform.machine().lower()
    arch = {"amd64": "x64", "x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(arch, arch)
    return f"rsa-{version}-{os_name}-{arch}"


def main() -> int:
    sys.path.insert(0, str(ROOT))
    from rsa import __version__

    name = target_name(__version__)
    suffix = ".exe" if platform.system() == "Windows" else ""
    release = ROOT / "release"
    release.mkdir(exist_ok=True)
    env = dict(os.environ, RSA_EXE_NAME=name)
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
           "--distpath", str(release), "--workpath", str(ROOT / "build" / "pyinstaller"), str(ROOT / "rsa.spec")]
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=ROOT, env=env)

    exe = release / f"{name}{suffix}"
    if not exe.exists():
        print(f"error: expected {exe} after the build", file=sys.stderr)
        return 1
    plain = release / f"rsa{suffix}"
    shutil.copy2(exe, plain)
    out = subprocess.run([str(exe), "--version"], capture_output=True, text=True, check=True).stdout.strip()
    print(f"\nBuilt {exe} ({exe.stat().st_size / 1e6:.1f} MB), reports version {out}")
    print(f"Copied to {plain}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
