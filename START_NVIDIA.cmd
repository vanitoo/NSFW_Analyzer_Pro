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

echo Installing experimental general classifier...
python -m pip install -r requirements-general.txt || exit /b 1

echo Installing clean CUDA ONNX Runtime...
python -m pip uninstall -y onnxruntime onnxruntime-gpu >nul 2>nul
python -m pip install --no-cache-dir "onnxruntime-gpu[cuda,cudnn]==1.26.0" || exit /b 1

echo Checking installed dependencies...
python -m pip check || exit /b 1

echo.
python -c "import torch; print('PyTorch CUDA available:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU only')"
python -c "import onnxruntime as ort; getattr(ort, 'preload_dlls', lambda **kwargs: None)(); p=ort.get_available_providers(); print('ONNX Runtime providers:', p); assert 'CUDAExecutionProvider' in p, 'CUDAExecutionProvider is not available after GPU install'"
echo.
echo Starting NSFW Analyzer Pro...
python main.py
endlocal
