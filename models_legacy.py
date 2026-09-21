from __future__ import annotations

import os
import shutil
import threading
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Callable

import numpy as np
from PIL import Image

from utils import get_cpu_cores

CACHE_DIR = Path.home() / ".cache" / "nsfw-analyzer-pro"
GANTMAN_VERSION = "1.2.0"
GANTMAN_RELEASE_URL = (
    "https://github.com/GantMan/nsfw_model/releases/download/"
    "1.2.0/mobilenet_v2_140_224.1.zip"
)
GANTMAN_ARCHIVE = CACHE_DIR / "downloads" / "gantman-1.2.0.zip"
GANTMAN_ROOT = CACHE_DIR / "gantman" / GANTMAN_VERSION
GANTMAN_LABELS = ("drawings", "hentai", "neutral", "porn", "sexy")
GANTMAN_UNSAFE = (1, 3, 4)


def tensorflow_device_name() -> tuple[str, int]:
    """Return the active TensorFlow device description and a safe worker count."""
    import tensorflow as tf

    gpu_devices = tf.config.list_physical_devices("GPU")
    if gpu_devices:
        return f"TensorFlow GPU: {gpu_devices[0].name}", 1
    return "TensorFlow CPU", 2


def _safe_extract_zip(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with zipfile.ZipFile(archive, "r") as zip_ref:
        for member in zip_ref.infolist():
            target = (destination / member.filename).resolve()
            if os.path.commonpath((str(root), str(target))) != str(root):
                raise RuntimeError(f"Небезопасный путь в архиве GantMan: {member.filename}")
        zip_ref.extractall(destination)


def _find_gantman_tflite(root: Path) -> Path | None:
    matches = sorted(root.rglob("saved_model.tflite"))
    return matches[0] if matches else None


def _ensure_gantman_tflite(log: Callable[[Any, str], None], self: Any) -> Path:
    cached = _find_gantman_tflite(GANTMAN_ROOT)
    if cached is not None:
        return cached

    GANTMAN_ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    if not GANTMAN_ARCHIVE.exists():
        log(
            self,
            "[GantMan] Скачиваем официальный release 1.2.0 (~100 MB). "
            "Это выполняется один раз.\n",
        )
        urllib.request.urlretrieve(GANTMAN_RELEASE_URL, str(GANTMAN_ARCHIVE))

    temp_root = GANTMAN_ROOT.with_name(f"{GANTMAN_ROOT.name}.tmp")
    shutil.rmtree(temp_root, ignore_errors=True)
    temp_root.parent.mkdir(parents=True, exist_ok=True)

    log(self, "[GantMan] Распаковываем TFLite-модель в локальный cache...\n")
    _safe_extract_zip(GANTMAN_ARCHIVE, temp_root)

    candidate = _find_gantman_tflite(temp_root)
    if candidate is None:
        shutil.rmtree(temp_root, ignore_errors=True)
        raise RuntimeError(
            "В официальном архиве GantMan 1.2.0 не найден saved_model.tflite"
        )

    shutil.rmtree(GANTMAN_ROOT, ignore_errors=True)
    temp_root.replace(GANTMAN_ROOT)

    cached = _find_gantman_tflite(GANTMAN_ROOT)
    if cached is None:
        raise RuntimeError("Не удалось подготовить TFLite-модель GantMan")
    return cached


def _resize_for_tflite(path: str, input_detail: dict[str, Any]) -> np.ndarray:
    shape = [int(value) for value in input_detail["shape"]]
    if len(shape) != 4 or shape[0] not in (1, -1):
        raise RuntimeError(f"Неожиданная форма входа GantMan: {shape}")

    if shape[-1] in (1, 3, 4):
        height, width = shape[1], shape[2]
        channels_first = False
    elif shape[1] in (1, 3, 4):
        height, width = shape[2], shape[3]
        channels_first = True
    else:
        raise RuntimeError(f"Не удалось определить layout входа GantMan: {shape}")

    if height <= 0 or width <= 0:
        height = width = 224

    with Image.open(path) as image:
        image = image.convert("RGB").resize((width, height), Image.Resampling.BILINEAR)
        array = np.asarray(image, dtype=np.float32) / 255.0

    if channels_first:
        array = np.transpose(array, (2, 0, 1))

    array = np.expand_dims(array, axis=0)
    dtype = input_detail["dtype"]

    if np.issubdtype(dtype, np.floating):
        return array.astype(dtype, copy=False)

    scale, zero_point = input_detail.get("quantization", (0.0, 0))
    if not scale:
        raise RuntimeError("Квантованный вход GantMan не содержит scale")
    info = np.iinfo(dtype)
    quantized = np.rint(array / scale + zero_point)
    quantized = np.clip(quantized, info.min, info.max)
    return quantized.astype(dtype)


def _dequantize_output(output: np.ndarray, detail: dict[str, Any]) -> np.ndarray:
    values = np.asarray(output).reshape(-1)
    if np.issubdtype(values.dtype, np.floating):
        return values.astype(np.float32, copy=False)

    scale, zero_point = detail.get("quantization", (0.0, 0))
    if not scale:
        return values.astype(np.float32)
    return (values.astype(np.float32) - float(zero_point)) * float(scale)


def initialize_gantman(
    self: Any,
    log: Callable[[Any, str], None],
) -> None:
    """Run the official GantMan 1.2.0 TFLite export on TensorFlow 2.20."""
    import tensorflow as tf

    model_path = _ensure_gantman_tflite(log, self)
    num_threads = max(1, min(4, get_cpu_cores()))

    interpreter = tf.lite.Interpreter(
        model_path=str(model_path),
        num_threads=num_threads,
    )
    interpreter.allocate_tensors()

    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()
    if len(input_details) != 1 or not output_details:
        raise RuntimeError(
            f"Неожиданная сигнатура GantMan TFLite: "
            f"inputs={len(input_details)}, outputs={len(output_details)}"
        )

    input_detail = input_details[0]
    output_detail = output_details[0]
    invoke_lock = threading.Lock()

    def predict(path: str) -> tuple[float, str | None]:
        image = _resize_for_tflite(path, input_detail)
        with invoke_lock:
            interpreter.set_tensor(input_detail["index"], image)
            interpreter.invoke()
            raw_output = interpreter.get_tensor(output_detail["index"])

        scores = _dequantize_output(raw_output, output_detail)
        if scores.size < len(GANTMAN_LABELS):
            raise RuntimeError(f"Неожиданный размер выхода GantMan: {scores.shape}")

        scores = scores[: len(GANTMAN_LABELS)]
        label_index = int(np.argmax(scores))
        label = GANTMAN_LABELS[label_index]
        unsafe_score = float(max(scores[index] for index in GANTMAN_UNSAFE))
        return unsafe_score, label

    self.model = interpreter
    self.model_aux = {
        "model_path": str(model_path),
        "source": f"GantMan release {GANTMAN_VERSION}",
        "runtime": "TensorFlow Lite",
    }
    self.predict_fn = predict
    self.compute_device = f"TensorFlow Lite CPU/XNNPACK ({num_threads} threads)"
    self.inference_workers = 1
