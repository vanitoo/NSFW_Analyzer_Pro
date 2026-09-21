from __future__ import annotations

import os
import shutil
import threading
import time
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

_CACHE_DIR = Path.home() / ".cache" / "nsfw-analyzer-pro"
os.environ.setdefault("TFHUB_CACHE_DIR", str(_CACHE_DIR / "tfhub"))
os.environ.setdefault("OPENNSFW2_HOME", str(_CACHE_DIR / "opennsfw2"))

import keras
import numpy as np
import tensorflow as tf

from models_extra import (
    MODEL_FREEPIK,
    MODEL_MARQO,
    MODEL_NUDENET,
    initialize_extra_model,
    release_extra_model,
)
from utils import get_cpu_cores

MODEL_YAHOO = "Yahoo NSFW"
MODEL_GANTMAN = "GantMan NSFW"
MODEL_HUB = "NSFW Hub Detector"
MODEL_CHOICES = (
    MODEL_YAHOO,
    MODEL_MARQO,
    MODEL_FREEPIK,
    MODEL_NUDENET,
    MODEL_GANTMAN,
    MODEL_HUB,
)

_MODEL_URL = "https://github.com/GantMan/nsfw_model/archive/refs/heads/master.zip"
_GANTMAN_DIR = Path("nsfw_model_mobilenet_v2")
_GANTMAN_SAVED_MODEL = _GANTMAN_DIR / "mobilenet_v2_140_224"
_GANTMAN_ZIP = Path("nsfw_model.zip")
_GANTMAN_TMP = Path("gantman_tmp")
_GANTMAN_LABELS = ("drawings", "hentai", "neutral", "porn", "sexy")
_GANTMAN_UNSAFE = (1, 3, 4)


def _emit(self: Any, event: str, *payload: Any) -> None:
    """Send a thread-safe event to the Tk main thread."""
    self.image_queue.put((event, *payload))


def _log(self: Any, message: str) -> None:
    _emit(self, "log", message)


def _normalize_model_name(model_name: str) -> str:
    name = model_name.strip().lower()
    if "yahoo" in name:
        return "yahoo"
    if "marqo" in name:
        return "marqo"
    if "freepik" in name:
        return "freepik"
    if "nudenet" in name:
        return "nudenet"
    if "gantman" in name:
        return "gantman"
    if "nsfw hub" in name:
        return "nsfw_hub"
    raise ValueError(f"Неизвестная модель: {model_name}")


def _decode_image(img_path: str, size: tuple[int, int] = (224, 224)) -> tf.Tensor:
    """Decode JPEG/PNG/BMP/GIF (first frame) into a resized RGB tensor."""
    raw = tf.io.read_file(img_path)
    image = tf.io.decode_image(raw, channels=3, expand_animations=False)
    image.set_shape((None, None, 3))
    return tf.image.resize(image, size)


def _safe_extract_zip(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    destination_resolved = destination.resolve()
    with zipfile.ZipFile(archive, "r") as zip_ref:
        for member in zip_ref.infolist():
            target = (destination / member.filename).resolve()
            if os.path.commonpath((destination_resolved, target)) != str(destination_resolved):
                raise RuntimeError(f"Небезопасный путь в архиве: {member.filename}")
        zip_ref.extractall(destination)


def initialize_model(self: Any, model_name: str) -> None:
    """Initialize or switch the inference backend exactly once per selected model."""
    normalized = _normalize_model_name(model_name)
    if getattr(self, "model_name", None) == normalized and getattr(self, "predict_fn", None) is not None:
        return

    if not hasattr(self, "model_lock"):
        self.model_lock = threading.Lock()

    with self.model_lock:
        if getattr(self, "model_name", None) == normalized and getattr(self, "predict_fn", None) is not None:
            return

        release_extra_model(self)
        self.model = None
        self.predict_fn = None
        self.model_name = normalized
        self.compute_device = "CPU"
        self.inference_workers = 2
        _log(self, f"Инициализация модели: {model_name}\n")

        try:
            if normalized == "yahoo":
                import opennsfw2

                self.model = opennsfw2
                self.predict_fn = lambda path: (float(opennsfw2.predict_image(path)), None)

            elif normalized in {"marqo", "freepik", "nudenet"}:
                initialize_extra_model(self, normalized, _log)

            elif normalized == "gantman":
                _initialize_gantman(self)
                gpu_devices = tf.config.list_physical_devices("GPU")
                self.compute_device = f"TensorFlow GPU: {gpu_devices[0].name}" if gpu_devices else "TensorFlow CPU"
                self.inference_workers = 1 if gpu_devices else 2

            elif normalized == "nsfw_hub":
                import tensorflow_hub as hub

                self.model = hub.load("https://tfhub.dev/GourmetAI/nsfw_classifier/1")

                def predict_hub(path: str) -> tuple[float, str | None]:
                    image = _decode_image(path)
                    image = tf.cast(image, tf.float32) / 255.0
                    image = tf.expand_dims(image, axis=0)
                    outputs = self.model(image)
                    if isinstance(outputs, dict):
                        preds = np.asarray(next(iter(outputs.values()))).reshape(-1)
                    else:
                        preds = np.asarray(outputs).reshape(-1)
                    if preds.size < 5:
                        raise RuntimeError(f"Неожиданный размер выхода NSFW Hub: {preds.shape}")
                    score = float(max(preds[1], preds[3], preds[4]))
                    return score, None

                self.predict_fn = predict_hub
                gpu_devices = tf.config.list_physical_devices("GPU")
                self.compute_device = f"TensorFlow GPU: {gpu_devices[0].name}" if gpu_devices else "TensorFlow CPU"
                self.inference_workers = 1 if gpu_devices else 2

            if normalized == "yahoo":
                gpu_devices = tf.config.list_physical_devices("GPU")
                self.compute_device = f"TensorFlow GPU: {gpu_devices[0].name}" if gpu_devices else "TensorFlow CPU"
                self.inference_workers = 1 if gpu_devices else 2

            _log(self, f"[{model_name}] ✅ Модель готова | устройство: {self.compute_device}\n")
        except Exception:
            self.model = None
            self.predict_fn = None
            self.model_name = None
            raise


def _initialize_gantman(self: Any) -> None:
    if not _GANTMAN_SAVED_MODEL.exists():
        _GANTMAN_DIR.mkdir(parents=True, exist_ok=True)
        if not _GANTMAN_ZIP.exists():
            _log(self, "[GantMan] Скачиваем модель (~90 MB)...\n")
            urllib.request.urlretrieve(_MODEL_URL, _GANTMAN_ZIP)

        if _GANTMAN_TMP.exists():
            shutil.rmtree(_GANTMAN_TMP)
        _log(self, "[GantMan] Распаковываем модель...\n")
        _safe_extract_zip(_GANTMAN_ZIP, _GANTMAN_TMP)

        source = _GANTMAN_TMP / "nsfw_model-master" / "mobilenet_v2_140_224"
        if not source.exists():
            raise RuntimeError("В архиве GantMan не найден SavedModel")
        shutil.move(str(source), str(_GANTMAN_SAVED_MODEL))
        shutil.rmtree(_GANTMAN_TMP, ignore_errors=True)

    self.model = keras.layers.TFSMLayer(str(_GANTMAN_SAVED_MODEL), call_endpoint="serving_default")

    def predict_gantman(path: str) -> tuple[float, str | None]:
        image = _decode_image(path)
        image = tf.cast(image, tf.float32) / 255.0
        image = tf.expand_dims(image, axis=0)
        outputs = self.model(image)
        if isinstance(outputs, dict):
            scores = np.asarray(next(iter(outputs.values()))).reshape(-1)
        else:
            scores = np.asarray(outputs).reshape(-1)
        if scores.size < len(_GANTMAN_LABELS):
            raise RuntimeError(f"Неожиданный размер выхода GantMan: {scores.shape}")

        label_index = int(np.argmax(scores[: len(_GANTMAN_LABELS)]))
        label = _GANTMAN_LABELS[label_index]
        unsafe_score = float(max(scores[index] for index in _GANTMAN_UNSAFE))
        return unsafe_score, label

    self.predict_fn = predict_gantman


def is_nude_image(
    self: Any,
    img_path: str,
    threshold: float,
    model_name: str,
) -> tuple[float, bool | None, str | None, str | None]:
    """Return score, decision, bad flag, and optional category."""
    try:
        initialize_model(self, model_name)
        if self.predict_fn is None:
            raise RuntimeError("Модель не инициализирована")
        score, category = self.predict_fn(img_path)
        return score, score >= threshold, None, category
    except (OSError, ValueError, tf.errors.OpError) as exc:
        _log(self, f"[SKIP] Не удалось обработать {img_path}: {exc}\n")
        return 0.0, None, "BAD", None
    except Exception as exc:
        _log(self, f"[SKIP] Ошибка анализа {img_path}: {exc}\n")
        return 0.0, None, "BAD", None


def analyze_images(
    self: Any,
    items: list[tuple[str, str]],
    threshold: float,
    model_name: str,
) -> None:
    """Analyze a UI snapshot without touching Tk widgets from worker threads."""
    total_items = len(items)
    if total_items == 0:
        _emit(self, "status", "Нет изображений для анализа")
        _emit(self, "analysis_complete", "empty")
        return

    start_total = time.perf_counter()

    try:
        initialize_model(self, model_name)
    except Exception as exc:
        _log(self, f"❌ Ошибка инициализации модели: {exc}\n")
        _emit(self, "analysis_error", str(exc))
        return

    max_workers = max(
        1,
        min(int(getattr(self, "inference_workers", 2)), get_cpu_cores(), total_items),
    )

    _log(
        self,
        f"▶ Модель: {model_name} | устройство: {getattr(self, 'compute_device', 'unknown')} | "
        f"worker'ов: {max_workers} | файлов: {total_items}\n",
    )
    _emit(self, "progress_setup", total_items)

    def process_item(item_id: str, img_path: str):
        if self.stop_analysis or not self.running:
            return None
        started = time.perf_counter()
        score, decision, bad_flag, category = is_nude_image(self, img_path, threshold, model_name)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        return item_id, img_path, score, decision, bad_flag, category, elapsed_ms

    processed = 0
    nude_count = 0
    safe_count = 0
    bad_count = 0

    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="nsfw") as executor:
        futures = [executor.submit(process_item, item_id, path) for item_id, path in items]
        for future in as_completed(futures):
            if not self.running:
                break

            result = future.result()
            if result is None:
                continue

            item_id, img_path, score, decision, bad_flag, category, elapsed_ms = result
            processed += 1

            if bad_flag == "BAD" or decision is None:
                bad_count += 1
                status = "BAD"
                tag = "bad"
                detail = "BAD"
            elif decision:
                nude_count += 1
                status = "✓"
                tag = "nude"
                detail = "НЮ"
            else:
                safe_count += 1
                status = "✗"
                tag = "safe"
                detail = "безопасно"

            _emit(
                self,
                "update_item",
                item_id,
                {"Оценка": f"{score:.4f}", "Статус": status, "tag": tag},
            )
            category_text = f" | категория: {category}" if category else ""
            _log(
                self,
                f"⏱ {os.path.basename(img_path)}: {elapsed_ms:.1f} ms | "
                f"{score:.4f} — {detail}{category_text}\n",
            )
            _emit(self, "status", f"Анализ изображений... ({processed} / {total_items})")
            _emit(self, "progress", processed)

            if self.stop_analysis:
                for pending in futures:
                    pending.cancel()
                break

    elapsed = time.perf_counter() - start_total
    if self.stop_analysis:
        _log(self, f"⛔ Анализ остановлен: обработано {processed} из {total_items}\n")
        _emit(self, "status", f"Анализ остановлен ({processed}/{total_items})")
        _emit(self, "analysis_complete", "stopped")
        return

    report = (
        "\n📊 Результаты анализа\n"
        f"Всего обработано: {processed}\n"
        f"НЮ: {nude_count}\n"
        f"Безопасные: {safe_count}\n"
        f"BAD: {bad_count}\n"
        f"⏱ Общее время: {elapsed:.2f} с\n"
    )
    _log(self, report)
    _emit(self, "status", "Анализ завершен")
    _emit(self, "analysis_complete", "done")
