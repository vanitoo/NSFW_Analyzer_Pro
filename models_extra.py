from __future__ import annotations

import gc
import sys
from pathlib import Path
from typing import Any, Callable

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
    log(self, "[Marqo] При первом запуске веса (~22 MB) будут загружены с Hugging Face.\n")

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
    log(self, "[Freepik] При первом запуске веса (~173 MB) будут загружены с Hugging Face.\n")

    classifier = pipeline(
        "image-classification",
        model="Freepik/nsfw_image_detector",
        device=pipeline_device,
    )

    def predict(path: str) -> tuple[float, str | None]:
        with Image.open(path) as image:
            predictions = classifier(image.convert("RGB"), top_k=None)

        scores = {str(item["label"]).lower(): float(item["score"]) for item in predictions}
        # Freepik documents medium-or-higher as the useful binary NSFW cut.
        score = min(1.0, scores.get("medium", 0.0) + scores.get("high", 0.0))
        category = max(scores, key=scores.get) if scores else "unknown"
        return score, f"{category} (medium+high={score:.3f})"

    self.model = classifier
    self.predict_fn = predict
    self.compute_device = device_name
    self.inference_workers = 1


def _initialize_nudenet(self: Any, log: Callable[[Any, str], None]) -> None:
    try:
        import nudenet
        import onnxruntime as ort
        from nudenet import NudeDetector
    except ImportError as exc:
        raise RuntimeError(
            "Для NudeNet нужны nudenet и onnxruntime. Выполните: pip install -r requirements-models.txt"
        ) from exc

    log(self, "[NudeNet] Модель 320n входит в пакет; отдельная загрузка весов не нужна.\n")
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
        summary = ", ".join(
            f"{item.get('class', '?')}:{float(item.get('score', 0.0)):.2f}"
            for item in explicit[:3]
        )
        return score, summary

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
