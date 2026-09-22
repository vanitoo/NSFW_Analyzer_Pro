from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

from .paths import (
    CACHE_DIR,
    GANTMAN_CACHE_DIR,
    HUGGINGFACE_CACHE_DIR,
    OPENCLIP_CACHE_DIR,
    OPENNSFW2_WEIGHTS,
    PROJECT_ROOT,
    RAMPP_CACHE_DIR,
    TFHUB_CACHE_DIR,
)


def _size_bytes(path: Path) -> int:
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    if not path.exists():
        return 0

    total = 0
    try:
        for item in path.rglob("*"):
            if item.is_file():
                try:
                    total += item.stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


def _format_size(size_bytes: int) -> str:
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def _hf_repo_dir(repo_id: str) -> Path:
    return HUGGINGFACE_CACHE_DIR / "hub" / ("models--" + repo_id.replace("/", "--"))


def _cached_line(name: str, path: Path) -> str:
    size = _size_bytes(path)
    if size > 0:
        return f"  ✅ {name}: кэш найден ({_format_size(size)})"
    return f"  ⬇ {name}: кэш не загружен"


def _module_line(label: str, module_name: str, install_hint: str = "") -> str:
    if importlib.util.find_spec(module_name) is not None:
        return f"  ✅ {label}: установлен"
    suffix = f" — {install_hint}" if install_hint else ""
    return f"  ❌ {label}: не установлен{suffix}"


def _nudenet_line() -> str:
    spec = importlib.util.find_spec("nudenet")
    if spec is None:
        return "  ❌ NudeNet: пакет не установлен"

    candidates: list[Path] = []
    if spec.submodule_search_locations:
        candidates.extend(Path(location) / "320n.onnx" for location in spec.submodule_search_locations)
    if spec.origin:
        candidates.append(Path(spec.origin).resolve().parent / "320n.onnx")

    for path in candidates:
        if path.exists():
            return f"  ✅ NudeNet: встроенная модель ({_format_size(_size_bytes(path))})"
    return "  ⚠ NudeNet: пакет установлен, 320n.onnx не найден"


def _tfhub_cached() -> tuple[bool, int]:
    if not TFHUB_CACHE_DIR.exists():
        return False, 0
    try:
        cached = any(TFHUB_CACHE_DIR.rglob("saved_model.pb"))
    except OSError:
        cached = False
    return cached, _size_bytes(TFHUB_CACHE_DIR)


def _nvidia_smi_line() -> str:
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,driver_version",
                "--format=csv,noheader",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return "  ❌ NVIDIA driver: nvidia-smi не найден"

    line = completed.stdout.strip().splitlines()
    if completed.returncode == 0 and line:
        return f"  ✅ NVIDIA driver: {line[0]}"
    return "  ❌ NVIDIA driver: GPU не обнаружен"


def _pytorch_cuda_line() -> str:
    if importlib.util.find_spec("torch") is None:
        return "  ❌ PyTorch CUDA: torch не установлен"
    try:
        import torch

        if torch.cuda.is_available():
            index = torch.cuda.current_device()
            return (
                f"  ✅ PyTorch CUDA: {torch.cuda.get_device_name(index)} "
                f"(CUDA runtime {torch.version.cuda or '?'})"
            )
        return "  ❌ PyTorch CUDA: недоступна"
    except Exception as exc:
        return f"  ⚠ PyTorch CUDA: ошибка проверки: {exc}"


def _onnx_cuda_line() -> str:
    if importlib.util.find_spec("onnxruntime") is None:
        return "  ❌ ONNX CUDA: onnxruntime не установлен"
    try:
        import onnxruntime as ort

        if hasattr(ort, "preload_dlls"):
            try:
                ort.preload_dlls()
            except Exception:
                pass
        providers = ort.get_available_providers()
        if "CUDAExecutionProvider" in providers:
            return "  ✅ ONNX CUDA: CUDAExecutionProvider доступен"
        return f"  ❌ ONNX CUDA: недоступна ({', '.join(providers)})"
    except Exception as exc:
        return f"  ⚠ ONNX CUDA: ошибка проверки: {exc}"


def build_startup_report() -> str:
    """Build a compact startup report without loading any inference model."""
    gantman = next(iter(GANTMAN_CACHE_DIR.rglob("saved_model.tflite")), None) if GANTMAN_CACHE_DIR.exists() else None
    tfhub_cached, tfhub_size = _tfhub_cached()

    lines = [
        "",
        "=== NSFW Analyzer Pro: состояние моделей ===",
        f"Кэш: {CACHE_DIR}",
        _cached_line("Yahoo/OpenNSFW2", OPENNSFW2_WEIGHTS),
        _cached_line("Marqo Fast", _hf_repo_dir("Marqo/nsfw-image-detection-384")),
        _cached_line("Freepik 4-Level", _hf_repo_dir("Freepik/nsfw_image_detector")),
        _cached_line("MobileCLIP2-S0/S2", OPENCLIP_CACHE_DIR),
        _cached_line("RAM++ checkpoint", RAMPP_CACHE_DIR),
        _nudenet_line(),
        (
            f"  ✅ GantMan: кэш найден ({_format_size(_size_bytes(gantman))})"
            if gantman is not None
            else "  ⬇ GantMan: кэш не загружен"
        ),
        (
            f"  ✅ NSFW Hub: кэш найден ({_format_size(tfhub_size)})"
            if tfhub_cached
            else "  ⬇ NSFW Hub: кэш не загружен"
        ),
        "",
        "Runtime:",
        _module_line("TensorFlow", "tensorflow"),
        _module_line("TensorFlow Hub", "tensorflow_hub", "запустите START.cmd / START_NVIDIA.cmd"),
        _module_line("PyTorch", "torch"),
        _module_line("OpenCLIP", "open_clip", "pip install -r requirements-general.txt"),
        (
            "  ✅ RAM++ runtime: .venv-rampp найден"
            if (
                (PROJECT_ROOT / ".venv-rampp" / "Scripts" / "python.exe").exists()
                or (PROJECT_ROOT / ".venv-rampp" / "bin" / "python").exists()
            )
            else "  ❌ RAM++ runtime: не установлен — запустите SETUP_RAMPP.cmd"
        ),
        _module_line("ONNX Runtime", "onnxruntime"),
        "",
        "CUDA:",
        _nvidia_smi_line(),
        _pytorch_cuda_line(),
        _onnx_cuda_line(),
    ]

    if sys.platform.startswith("win"):
        lines.append("  ℹ TensorFlow 2.20: native Windows CUDA не используется; Yahoo/Hub работают на CPU")
    lines.append("=== конец отчёта ===")
    lines.append("")
    return "\n".join(lines)
