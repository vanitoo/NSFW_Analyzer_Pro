import os
import time
import threading
import urllib.request
import zipfile
import shutil
import datetime
from concurrent.futures import ThreadPoolExecutor

import tensorflow as tf
import keras
from PIL import Image

from utils import get_cpu_cores, log_message, convert_size


class AnalyzerWorker:
    def __init__(self, log_console=None, image_queue=None):
        self.log_console = log_console
        self.image_queue = image_queue

        self.stop_analysis = False
        self.running = False

        self.model = None
        self.model_name = ""
        self.predict_fn = None
        self.model_lock = threading.Lock()

        self.all_files = []
        self.threshold = 0.8

        # поддерживаемые форматы
        self.supported_formats = (".png", ".jpg", ".jpeg", ".bmp", ".gif")

    # ----------------------------- ПРЕДОБРАБОТКА -----------------------------
    def load_and_preprocess(self, path, target_size=(224, 224)):
        """Ускоренная загрузка через Pillow с draft для экономии времени"""
        img = Image.open(path)
        img.draft("RGB", target_size)
        img = img.convert("RGB")
        img = img.resize(target_size, Image.BILINEAR)
        return tf.convert_to_tensor(img, dtype=tf.float32) / 255.0

    # ----------------------------- ИНИЦИАЛИЗАЦИЯ МОДЕЛЕЙ -----------------------------
    def initialize_model(self, model_name: str):
        """Инициализация модели по имени"""
        # очищаем старую модель
        self.model = None
        self.predict_fn = None
        self.model_name = model_name.lower()

        log_message(f"Инициализация модели: {self.model_name}\n", self.log_console)

        try:
            if "yahoo" in self.model_name:
                import opennsfw2
                self.model = opennsfw2
                self.predict_fn = lambda path: float(self.model.predict_image(path))
                log_message("[Yahoo] ✅ Модель готова к работе\n", self.log_console)

            elif "gantman" in self.model_name:
                log_message("[GantMan] Инициализация...\n", self.log_console)
                self._initialize_model_gantman()

            elif "mobilenet" in self.model_name:
                from tensorflow.keras.applications.mobilenet_v2 import preprocess_input
                log_message("[MobileNetV2] Загрузка модели...\n", self.log_console)
                self.model = tf.keras.applications.MobileNetV2(weights='imagenet')
                self.preprocess_input = preprocess_input
                self.predict_fn = self._predict_mobilenet
                log_message("[MobileNetV2] ✅ Модель готова к работе\n", self.log_console)

            elif "nsfw hub" in self.model_name:
                import tensorflow_hub as hub
                log_message("[NSFW Hub] Загрузка модели...\n", self.log_console)
                self.model = hub.load("https://tfhub.dev/GourmetAI/nsfw_classifier/1")
                self.predict_fn = self._predict_nsfw_hub
                log_message("[NSFW Hub] ✅ Модель готова к работе\n", self.log_console)

            else:
                log_message(f"❌ Неизвестная модель: {self.model_name}\n", self.log_console)
                self.model = None
                self.predict_fn = None

        except Exception as e:
            log_message(f"❌ Ошибка инициализации модели: {str(e)}\n", self.log_console)
            raise

    def _initialize_model_gantman(self):
        model_dir = "nsfw_model_mobilenet_v2"
        saved_model_path = os.path.join(model_dir, "mobilenet_v2_140_224")
        zip_path = "nsfw_model.zip"

        with self.model_lock:
            if not os.path.exists(saved_model_path):
                os.makedirs(model_dir, exist_ok=True)
                if not os.path.exists(zip_path):
                    log_message("[GantMan] Скачиваем NSFW модель (~90MB)...\n", self.log_console)
                    urllib.request.urlretrieve(
                        "https://github.com/GantMan/nsfw_model/archive/refs/heads/master.zip",
                        zip_path
                    )
                log_message("[GantMan] Распаковка модели...\n", self.log_console)
                tmp_dir = "gantman_tmp"
                if os.path.exists(tmp_dir):
                    shutil.rmtree(tmp_dir)
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(tmp_dir)
                shutil.move(os.path.join(tmp_dir, "nsfw_model-master", "mobilenet_v2_140_224"), saved_model_path)
                shutil.rmtree(tmp_dir)

            log_message(f"[GantMan] Загружаем модель из {saved_model_path}...\n", self.log_console)
            self.model = keras.layers.TFSMLayer(saved_model_path, call_endpoint='serving_default')
            self.predict_fn = self._predict_gantman
            log_message("✅ [GantMan] Модель готова к работе\n", self.log_console)

    # ----------------------------- PREDICT -----------------------------
    def _predict_gantman(self, img_path: str) -> float:
        img = self.load_and_preprocess(img_path)
        img = tf.expand_dims(img, 0)
        outputs = self.model(img)
        scores = list(outputs.values())[0].numpy()[0] if isinstance(outputs, dict) else outputs.numpy()[0]
        return float(max(scores[1], scores[3], scores[4]))

    def _predict_mobilenet(self, img_path: str) -> float:
        img = tf.io.read_file(img_path)
        img = tf.image.decode_jpeg(img, channels=3)
        img = tf.image.resize(img, [224, 224])
        img = self.preprocess_input(img)
        img = tf.expand_dims(img, axis=0)
        predictions = self.model.predict(img)
        return float(predictions[0][0])

    def _predict_nsfw_hub(self, img_path: str) -> float:
        img = tf.io.read_file(img_path)
        img = tf.image.decode_jpeg(img, channels=3)
        img = tf.image.resize(img, [224, 224])
        img = tf.cast(img, tf.float32) / 255.0
        img = tf.expand_dims(img, axis=0)
        preds = self.model(img).numpy()[0]
        return float(max(preds[1], preds[3], preds[4]))

    # ----------------------------- АНАЛИЗ -----------------------------
    def is_nude_image(self, img_path: str, threshold: float):
        try:
            start_time = time.time()
            score = self.predict_fn(img_path) if self.predict_fn else 0.0
            elapsed = (time.time() - start_time) * 1000.0
            log_message(f"⏱ Обработка {os.path.basename(img_path)} заняла {elapsed:.1f} ms | {score:.4f}\n", self.log_console)
            return score, score >= threshold
        except Exception as e:
            log_message(f"❌ Ошибка анализа {img_path}: {str(e)}\n", self.log_console)
            return 0.0, False

    def analyze_images(self, items, threshold):
        """Основной цикл анализа"""
        self.running = True
        self.stop_analysis = False
        start_total = time.time()
        total_items = len(items)
        processed_count = 0
        max_threads = min(16, get_cpu_cores())

        log_message(f"▶ Доступно ядер: {get_cpu_cores()} | Используем потоков: {max_threads}\n", self.log_console)

        def process_item(item_id, img_path):
            nonlocal processed_count
            if self.stop_analysis:
                return
            score, is_nude = self.is_nude_image(img_path, threshold)
            if self.image_queue:
                self.image_queue.put((
                    "update_item", item_id,
                    {"Порог": f"{score:.4f}", "НЮ": "✓" if is_nude else "✗", "tag": "nude" if is_nude else "safe"}
                ))
            processed_count += 1
            if self.image_queue:
                self.image_queue.put(("status", f"Анализ... ({processed_count}/{total_items})"))
                self.image_queue.put(("progress", processed_count))

        with ThreadPoolExecutor(max_workers=max_threads) as executor:
            for item_id, img_path in items:
                if self.stop_analysis:
                    break
                executor.submit(process_item, item_id, img_path)

        total_elapsed = time.time() - start_total
        if self.image_queue:
            self.image_queue.put(("log", f"\n⏱ Общее время анализа: {total_elapsed:.2f} сек\n"))
            self.image_queue.put(("status", "Анализ завершён"))
            self.image_queue.put(("analysis_complete", ""))

    # ----------------------------- СКАНИРОВАНИЕ -----------------------------
    def scan_folder_async(self, folder_path):
        """Асинхронное сканирование папки"""
        if self.image_queue:
            self.image_queue.put(("status", "Сканирование..."))
            self.image_queue.put(("progress_start", 0))

        file_count = 0
        batch = []

        for root, _, files in os.walk(folder_path):
            for file in files:
                if self.stop_analysis:
                    log_message("⛔ Сканирование прервано\n", self.log_console)
                    return
                if file.lower().endswith(self.supported_formats):
                    file_count += 1
                    img_path = os.path.join(root, file)
                    try:
                        stat = os.stat(img_path)
                        size = convert_size(stat.st_size)
                        mtime = datetime.datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M')
                        batch.append((file_count, os.path.basename(img_path), img_path, size, mtime, "", ""))

                        if len(batch) >= 100:
                            if self.image_queue:
                                self.image_queue.put(("update_file_list", batch.copy()))
                            batch.clear()
                    except Exception as e:
                        if self.image_queue:
                            self.image_queue.put(("log", f"Ошибка {img_path}: {e}\n"))

        if batch and self.image_queue:
            self.image_queue.put(("update_file_list", batch))

        if self.image_queue:
            self.image_queue.put(("scan_complete", file_count))
            self.image_queue.put(("status", f"Загружено {file_count} изображений"))
