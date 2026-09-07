@echo off
REM Builds release\rsa.exe (and release\rsa-<version>-windows-x64.exe) on this PC.
REM Needs Python 3.10+ from python.org with "Add python.exe to PATH" ticked.
REM No Python? Use GitHub instead: Actions -> "Build executables" -> Run workflow.
setlocal
REM Match the UTF-8 mode the packaged exe runs in, whatever the console code page is.
set PYTHONUTF8=1
cd /d "%~dp0"

if not exist .venv (
    py -3 -m venv .venv 2>nul || python -m venv .venv
    if errorlevel 1 (
        echo Could not create a virtual environment. Is Python installed and on PATH?
        pause
        exit /b 1
    )
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -e ".[dev,build]"
if errorlevel 1 goto :fail

python -m pytest -q
if errorlevel 1 goto :fail

python scripts\build_exe.py
if errorlevel 1 goto :fail

echo.
echo Done: release\rsa.exe  (double-click it for the menu, or run it from PowerShell: .\release\rsa.exe --help)
pause
exit /b 0

:fail
echo.
echo Build failed - see the messages above.
pause
exit /b 1
