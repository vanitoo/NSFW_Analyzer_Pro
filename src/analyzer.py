from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import numpy as np
from PIL import Image

from .models_extra import (
    MODEL_FREEPIK,
    MODEL_MARQO,
    MODEL_NUDENET,
    initialize_extra_model,
    release_extra_model,
)
from .models_legacy import ensure_opennsfw2_weights, initialize_gantman, tensorflow_device_name
from .paths import CACHE_DIR, TFHUB_CACHE_DIR
from .utils import get_cpu_cores

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

HUB_LABELS = ("drawings", "hentai", "neutral", "porn", "sexy")
MODEL_CATEGORY_CHOICES = {
    MODEL_YAHOO: ("NSFW", "SFW"),
    MODEL_MARQO: ("NSFW", "SFW"),
    MODEL_FREEPIK: ("neutral", "low", "medium", "high"),
    MODEL_NUDENET: (
        "ANUS_EXPOSED",
        "BUTTOCKS_EXPOSED",
        "FEMALE_BREAST_EXPOSED",
        "FEMALE_GENITALIA_EXPOSED",
        "MALE_GENITALIA_EXPOSED",
        "no explicit detections",
    ),
    MODEL_GANTMAN: HUB_LABELS,
    MODEL_HUB: HUB_LABELS,
}

STATUS_NUDE = "НЮ"
STATUS_SAFE = "Безопасно"
STATUS_BAD = "BAD"


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


def _decode_image(img_path: str, size: tuple[int, int] = (224, 224)) -> np.ndarray:
    """Decode a supported image with Pillow without importing TensorFlow."""
    with Image.open(img_path) as image:
        image = image.convert("RGB").resize((size[1], size[0]), Image.Resampling.BILINEAR)
        return np.asarray(image, dtype=np.float32)


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
        _log(self, f"Кэш моделей: {CACHE_DIR}\n")

        try:
            if normalized == "yahoo":
                import opennsfw2

                weights_path = ensure_opennsfw2_weights(self, _log)
                self.model = opennsfw2

                def predict_yahoo(path: str) -> tuple[float, str | None]:
                    score = float(opennsfw2.predict_image(path, weights_path=weights_path))
                    return score, "NSFW" if score >= 0.5 else "SFW"

                self.predict_fn = predict_yahoo

            elif normalized in {"marqo", "freepik", "nudenet"}:
                initialize_extra_model(self, normalized, _log)

            elif normalized == "gantman":
                initialize_gantman(self, _log)

            elif normalized == "nsfw_hub":
                import tensorflow as tf
                import tensorflow_hub as hub

                hub_cached = False
                try:
                    hub_cached = any(TFHUB_CACHE_DIR.rglob("saved_model.pb"))
                except OSError:
                    pass

                if hub_cached:
                    _log(self, "[NSFW Hub] кэш найден: 100% — загрузка не требуется\n")
                else:
                    _log(
                        self,
                        "[NSFW Hub] кэш не найден: этап 1/2 — скачивание и распаковка TensorFlow Hub...\n",
                    )

                self.model = hub.load("https://tfhub.dev/GourmetAI/nsfw_classifier/1")
                _log(self, "[NSFW Hub] этап 2/2 — модель загружена: 100%\n")

                def predict_hub(path: str) -> tuple[float, str | None]:
                    image = _decode_image(path) / 255.0
                    image = tf.convert_to_tensor(image[None, ...], dtype=tf.float32)
                    outputs = self.model(image)
                    if isinstance(outputs, dict):
                        preds = np.asarray(next(iter(outputs.values()))).reshape(-1)
                    else:
                        preds = np.asarray(outputs).reshape(-1)
                    if preds.size < 5:
                        raise RuntimeError(f"Неожиданный размер выхода NSFW Hub: {preds.shape}")
                    score = float(max(preds[1], preds[3], preds[4]))
                    label_index = int(np.argmax(preds[: len(HUB_LABELS)]))
                    return score, HUB_LABELS[label_index]

                self.predict_fn = predict_hub
                self.compute_device, self.inference_workers = tensorflow_device_name()

            if normalized == "yahoo":
                self.compute_device, self.inference_workers = tensorflow_device_name()

            _log(self, f"[{model_name}] ✅ Модель готова | устройство: {self.compute_device}\n")
        except Exception:
            self.model = None
            self.predict_fn = None
            self.model_name = None
            raise


def reset_model(self: Any) -> None:
    """Release the current backend when the user switches models."""
    if not hasattr(self, "model_lock"):
        self.model_lock = threading.Lock()

    with self.model_lock:
        self.model = None
        self.predict_fn = None
        self.model_name = None
        release_extra_model(self)


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
    except (OSError, ValueError) as exc:
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

            if bad_flag == STATUS_BAD or decision is None:
                bad_count += 1
                status = STATUS_BAD
                tag = "bad"
                detail = STATUS_BAD
            elif decision:
                nude_count += 1
                status = STATUS_NUDE
                tag = "nude"
                detail = STATUS_NUDE
            else:
                safe_count += 1
                status = STATUS_SAFE
                tag = "safe"
                detail = STATUS_SAFE

            _emit(
                self,
                "update_item",
                item_id,
                {
                    "Оценка": f"{score:.4f}",
                    "Статус": status,
                    "Категория": category or "",
                    "tag": tag,
                },
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
