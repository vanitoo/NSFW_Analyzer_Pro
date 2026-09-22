from __future__ import annotations

import gc
import sys
from pathlib import Path
from typing import Any, Callable

from .paths import HUGGINGFACE_CACHE_DIR

MODEL_MARQO = "Marqo Fast"
MODEL_FREEPIK = "Freepik 4-Level"
MODEL_NUDENET = "NudeNet Detector"

NUDENET_EXPLICIT_CLASSES = {
    "ANUS_EXPOSED",
    "BUTTOCKS_EXPOSED",
    "FEMALE_BREAST_EXPOSED",
    "FEMALE_GENITALIA_EXPOSED",
    "MALE_GENITALIA_EXPOSED",
}


def release_extra_model(self: Any) -> None:
    """Release references and reclaim PyTorch CUDA cache when switching models."""
    for attr in ("model_transform", "model_processor", "model_aux"):
        if hasattr(self, attr):
            setattr(self, attr, None)

    gc.collect()
    torch_module = sys.modules.get("torch")
    if torch_module is not None:
        try:
            if torch_module.cuda.is_available():
                torch_module.cuda.empty_cache()
        except Exception:
            pass


def _hf_repo_cache_dir(repo_id: str) -> Path:
    return HUGGINGFACE_CACHE_DIR / "hub" / ("models--" + repo_id.replace("/", "--"))


def _ensure_hf_snapshot(
    repo_id: str,
    label: str,
    log: Callable[[Any, str], None],
    self: Any,
) -> str:
    try:
        from huggingface_hub import snapshot_download
        from tqdm.auto import tqdm
    except ImportError as exc:
        raise RuntimeError(
            "Для загрузки Hugging Face моделей нужны huggingface_hub и tqdm."
        ) from exc

    cache_dir = HUGGINGFACE_CACHE_DIR / "hub"
    repo_cache = _hf_repo_cache_dir(repo_id)

    try:
        snapshot = snapshot_download(
            repo_id=repo_id,
            cache_dir=str(cache_dir),
            local_files_only=True,
        )
        log(self, f"[{label}] кэш модели найден: 100% — загрузка не требуется\n")
        return str(snapshot)
    except Exception:
        pass

    log(self, f"[{label}] кэш не найден, начинаем загрузку с Hugging Face.\n")

    class LogTqdm(tqdm):
        def __init__(progress_self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            progress_self._last_logged_percent = -10

        def update(progress_self, n=1):
            result = super().update(n)
            total = progress_self.total or 0
            if total:
                percent = min(100, int(progress_self.n * 100 / total))
                if (
                    percent >= progress_self._last_logged_percent + 10
                    or percent == 100
                ):
                    description = str(progress_self.desc or label).strip()
                    log(self, f"[{label}] {description}: {percent}%\n")
                    progress_self._last_logged_percent = percent
            return result

    snapshot = snapshot_download(
        repo_id=repo_id,
        cache_dir=str(cache_dir),
        tqdm_class=LogTqdm,
    )

    size = 0
    try:
        size = sum(
            item.stat().st_size
            for item in repo_cache.rglob("*")
            if item.is_file()
        )
    except OSError:
        pass
    size_text = f" ({size / 1024 / 1024:.1f} MB)" if size else ""
    log(self, f"[{label}] загрузка: 100% — готово{size_text}\n")
    return str(snapshot)


def _torch_device() -> tuple[Any, str]:
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError(
            "Для этой модели нужен PyTorch. Выполните: pip install -r requirements-models.txt"
        ) from exc

    if torch.cuda.is_available():
        index = torch.cuda.current_device()
        return torch.device(f"cuda:{index}"), f"CUDA: {torch.cuda.get_device_name(index)}"
    return torch.device("cpu"), "CPU"


def _initialize_marqo(self: Any, log: Callable[[Any, str], None]) -> None:
    try:
        import timm
        import torch
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError(
            "Для Marqo нужны torch и timm. Выполните: pip install -r requirements-models.txt"
        ) from exc

    device, device_name = _torch_device()
    _ensure_hf_snapshot(
        "Marqo/nsfw-image-detection-384",
        "Marqo",
        log,
        self,
    )
    log(self, "[Marqo] загрузка runtime: создаём модель...\n")
    model = timm.create_model("hf_hub:Marqo/nsfw-image-detection-384", pretrained=True)
    model = model.eval().to(device)
    data_config = timm.data.resolve_model_data_config(model)
    transform = timm.data.create_transform(**data_config, is_training=False)

    def predict(path: str) -> tuple[float, str | None]:
        with Image.open(path) as image:
            tensor = transform(image.convert("RGB")).unsqueeze(0).to(device)
        with torch.inference_mode():
            probabilities = model(tensor).softmax(dim=-1)[0].detach().cpu().numpy()

        if probabilities.size < 2:
            raise RuntimeError(f"Неожиданный размер выхода Marqo: {probabilities.shape}")

        # Model config: index 0 = NSFW, index 1 = SFW.
        nsfw_score = float(probabilities[0])
        label = "NSFW" if probabilities[0] >= probabilities[1] else "SFW"
        return nsfw_score, label

    self.model = model
    self.model_transform = transform
    self.predict_fn = predict
    self.compute_device = device_name
    self.inference_workers = 1 if device.type == "cuda" else 2
    log(self, f"[Marqo] модель готова: 100% | {device_name}\n")


def _initialize_freepik(self: Any, log: Callable[[Any, str], None]) -> None:
    try:
        import torch
        from PIL import Image
        from transformers import pipeline
    except ImportError as exc:
        raise RuntimeError(
            "Для Freepik нужны torch и transformers. Выполните: pip install -r requirements-models.txt"
        ) from exc

    device, device_name = _torch_device()
    pipeline_device = device.index if device.type == "cuda" else -1
    snapshot_path = _ensure_hf_snapshot(
        "Freepik/nsfw_image_detector",
        "Freepik",
        log,
        self,
    )
    log(self, "[Freepik] загрузка runtime: создаём pipeline...\n")
    classifier = pipeline(
        "image-classification",
        model=snapshot_path,
        device=pipeline_device,
    )

    def predict(path: str) -> tuple[float, str | None]:
        with Image.open(path) as image:
            predictions = classifier(image.convert("RGB"), top_k=None)

        scores = {str(item["label"]).lower(): float(item["score"]) for item in predictions}
        # Freepik documents medium-or-higher as the useful binary NSFW cut.
        score = min(1.0, scores.get("medium", 0.0) + scores.get("high", 0.0))
        category = max(scores, key=scores.get) if scores else "unknown"
        return score, category

    self.model = classifier
    self.predict_fn = predict
    self.compute_device = device_name
    self.inference_workers = 1
    log(self, f"[Freepik] модель готова: 100% | {device_name}\n")


def _initialize_nudenet(self: Any, log: Callable[[Any, str], None]) -> None:
    try:
        import nudenet
        import onnxruntime as ort
        from nudenet import NudeDetector
    except ImportError as exc:
        raise RuntimeError(
            "Для NudeNet нужны nudenet и onnxruntime. Выполните: pip install -r requirements-models.txt"
        ) from exc

    log(self, "[NudeNet] загрузка: 100% — 320n.onnx уже входит в пакет.\n")
    if hasattr(ort, "preload_dlls"):
        try:
            ort.preload_dlls()
        except Exception:
            pass

    detector = NudeDetector()
    providers = ort.get_available_providers()
    compute_device = "CPU / ONNX Runtime"

    # NudeNet 3.4.2 accepts providers but does not pass them to InferenceSession.
    # Re-create the bundled model session explicitly when a CUDA provider is available.
    if "CUDAExecutionProvider" in providers:
        model_path = Path(nudenet.__file__).resolve().parent / "320n.onnx"
        if model_path.exists():
            detector.onnx_session = ort.InferenceSession(
                str(model_path),
                providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
            )
            compute_device = "CUDA / ONNX Runtime"

    def predict(path: str) -> tuple[float, str | None]:
        detections = detector.detect(path)
        explicit = [
            detection
            for detection in detections
            if str(detection.get("class", "")).upper() in NUDENET_EXPLICIT_CLASSES
        ]
        if not explicit:
            return 0.0, "no explicit detections"

        explicit.sort(key=lambda item: float(item.get("score", 0.0)), reverse=True)
        score = float(explicit[0].get("score", 0.0))
        category = str(explicit[0].get("class", "unknown"))
        return score, category

    self.model = detector
    self.predict_fn = predict
    self.compute_device = compute_device
    self.inference_workers = 1 if "CUDA" in compute_device else 2


def initialize_extra_model(
    self: Any,
    normalized_name: str,
    log: Callable[[Any, str], None],
) -> None:
    if normalized_name == "marqo":
        _initialize_marqo(self, log)
    elif normalized_name == "freepik":
        _initialize_freepik(self, log)
    elif normalized_name == "nudenet":
        _initialize_nudenet(self, log)
    else:
        raise ValueError(f"Неизвестная дополнительная модель: {normalized_name}")
