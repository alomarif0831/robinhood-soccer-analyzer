"""Stamp a version (e.g. v0.1.2 or 0.1.2) into pyproject.toml and rsa/__init__.py."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEMVER = re.compile(r"^\d+\.\d+\.\d+([-.][0-9A-Za-z.]+)?$")


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: set_version.py vX.Y.Z", file=sys.stderr)
        return 2
    v = argv[0].lstrip("v")
    if not SEMVER.match(v):
        print(f"error: '{argv[0]}' is not a version like v0.1.6", file=sys.stderr)
        return 1
    py = ROOT / "pyproject.toml"
    init = ROOT / "rsa" / "__init__.py"
    py.write_text(re.sub(r'^version = "[^"]*"', f'version = "{v}"', py.read_text(encoding="utf-8"), count=1, flags=re.M), encoding="utf-8")
    init.write_text(re.sub(r'^__version__ = "[^"]*"', f'__version__ = "{v}"', init.read_text(encoding="utf-8"), count=1, flags=re.M), encoding="utf-8")
    print(f"version set to {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
