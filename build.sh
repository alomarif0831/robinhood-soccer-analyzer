#!/usr/bin/env bash
# Builds release/rsa (and release/rsa-<version>-<os>-<arch>) on macOS or Linux.
# Needs Python 3.10+. The Windows .exe must be built on Windows (build.bat) or by
# the GitHub Actions workflow: PyInstaller does not cross-compile.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
    python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev,build]"
python -m pytest -q
python scripts/build_exe.py
echo
echo "Done: release/rsa  (run ./release/rsa --help)"
