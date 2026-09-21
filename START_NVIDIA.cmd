@echo off
setlocal
cd /d "%~dp0"
title NSFW Analyzer Pro - NVIDIA CUDA

where python >nul 2>nul
if errorlevel 1 (
    echo Python not found. Install Python 3.11 or newer and try again.
    exit /b 1
)

where nvidia-smi >nul 2>nul
if errorlevel 1 (
    echo NVIDIA driver / nvidia-smi not found.
    echo Falling back to the regular installer.
    call START.cmd
    exit /b %errorlevel%
)

if not exist .venv (
    echo Creating virtual environment...
    python -m venv .venv || exit /b 1
)

call .venv\Scripts\activate || exit /b 1

echo Updating pip...
python -m pip install --upgrade pip || exit /b 1

echo Installing PyTorch with CUDA 12.8 support...
python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128 || exit /b 1

echo Installing base dependencies...
python -m pip install -r requirements.txt || exit /b 1

echo Installing additional NSFW models...
python -m pip install -r requirements-models.txt || exit /b 1

echo.
python -c "import torch; print('PyTorch CUDA available:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU only')"
echo.
echo Starting NSFW Analyzer Pro...
python main.py
endlocal
