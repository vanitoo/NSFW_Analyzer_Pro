@echo off
setlocal
cd /d "%~dp0"
title NSFW Analyzer Pro - RAM++ Runtime Setup

set "PYTHON_CMD=python"
where py >nul 2>nul
if not errorlevel 1 (
    py -3.10 -c "import sys; print(sys.version)" >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=py -3.10"
)

echo Using Python command: %PYTHON_CMD%

if not exist .venv-rampp (
    echo Creating isolated RAM++ environment...
    %PYTHON_CMD% -m venv .venv-rampp || exit /b 1
)

call .venv-rampp\Scripts\activate || exit /b 1

echo Updating installer tools...
python -m pip install --upgrade pip setuptools wheel || exit /b 1

where nvidia-smi >nul 2>nul
if errorlevel 1 (
    echo Installing CPU PyTorch for RAM++...
    python -m pip install torch torchvision || exit /b 1
) else (
    echo Installing CUDA 12.8 PyTorch for RAM++...
    python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128 || exit /b 1
)

echo Installing isolated RAM++ dependencies...
python -m pip install "timm==0.4.12" "transformers>=4.25.1" "fairscale==0.4.4" scipy Pillow || exit /b 1
python -m pip install "clip @ git+https://github.com/openai/CLIP.git" || exit /b 1
python -m pip install --no-deps "git+https://github.com/xinyu1205/recognize-anything.git" || exit /b 1

echo.
python -c "import torch; from ram.models import ram_plus; print('RAM++ runtime OK'); print('CUDA:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU only')" || exit /b 1
echo.
echo RAM++ runtime is ready.
echo The ~3 GB checkpoint will be downloaded into the project cache on first RAM++ analysis.
endlocal
