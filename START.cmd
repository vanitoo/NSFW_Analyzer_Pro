@echo off
setlocal
cd /d "%~dp0"
title NSFW Analyzer Pro

where python >nul 2>nul
if errorlevel 1 (
    echo Python not found. Install Python 3.11 or newer and try again.
    exit /b 1
)

if not exist .venv (
    echo Creating virtual environment...
    python -m venv .venv || exit /b 1
)

call .venv\Scripts\activate || exit /b 1

echo Installing/updating base dependencies...
python -m pip install --disable-pip-version-check -r requirements.txt || exit /b 1

echo Installing/updating additional NSFW models...
python -m pip install --disable-pip-version-check -r requirements-models.txt || exit /b 1

echo Installing experimental general classifier...
python -m pip install --disable-pip-version-check -r requirements-general.txt || exit /b 1

echo Starting NSFW Analyzer Pro...
python main.py
endlocal
