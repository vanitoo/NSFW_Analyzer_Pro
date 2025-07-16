@echo off
title %cd%

if not exist .venv (
    echo Creating virtual environment...
    python -m venv .venv
)

echo Activating virtual environment...
call .venv\Scripts\activate

if not exist .venv\.setup_done (
    if exist requirements.txt (
        echo Updating pip and installing dependencies...
        python -m pip install --upgrade pip
        pip install -r requirements.txt
        echo. > .venv\.setup_done
    ) else (
        echo requirements.txt not found, skipping dependency installation.
    )
) else (
    echo Dependencies already installed, skipping installation.
)

if exist main.py (
    echo Starting program...
    python main.py
) else (
    echo main.py not found.
)

echo Done.
rem pause
