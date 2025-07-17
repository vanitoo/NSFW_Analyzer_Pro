# в начале analyzer.py
# from PIL import ImageFile
# ImageFile.LOAD_TRUNCATED_IMAGES = True

import os
import shutil
import threading
import time
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed

import keras
import tensorflow as tf
from tensorflow.keras.applications.mobilenet_v2 import decode_predictions

from utils import get_cpu_cores, log_message

model_lock = threading.Lock()


# ---------------------- ОСНОВНОЙ АНАЛИЗ ----------------------
def analyze_images2(self):
    # 🚫 Блокируем выбор фильтра, порога и модели
    self.filter_combobox.config(state="disabled")
    self.threshold_slider.config(state="disabled")
    self.model_combobox.config(state="disabled")

    threshold = self.threshold_slider.get()
    items = self.result_tree.get_children()
    total_items = len(items)
    processed_count = 0
    max_threads = min(16, get_cpu_cores())  # ✅ теперь используем все ядра

    # ✅ Начало замера общего времени
    start_total = time.time()

    log_message(f"▶ Доступно ядер: {get_cpu_cores()} | Используем потоков: {max_threads}\n", self.log_console)

    self.progress["value"] = 0
    self.progress["maximum"] = total_items
    self.progress.update()

    def process_item(item):
        nonlocal processed_count
        if self.stop_analysis or not self.running:
            return
        try:
            img_path = self.result_tree.item(item)['values'][2]
            start_time = time.time()  # начало замера времени для этого файла
            # score, is_nude = is_nude_image(self, img_path, threshold)
            score, is_nude, bad_flag = is_nude_image(self, img_path, threshold)
            elapsed = (time.time() - start_time) * 1000.0  # мс

            if bad_flag == "BAD":
                self.image_queue.put((
                    "update_item", item,
                    {
                        "Порог": f"{score:.4f}",
                        "Статус": "BAD",
                        "tag": "bad"
                    }
                ))
                return

            # теперь в лог сразу пишем и время, и результат
            self.image_queue.put((
                "update_item", item,
                {
                    "Порог": f"{score:.4f}",
                    "Статус": "✓" if is_nude else "✗",
                    "tag": "nude" if is_nude else "safe"
                }
            ))

            self.image_queue.put((
                "log",
                f"⏱ Обработка {os.path.basename(img_path)} заняла {elapsed:.1f} ms | "
                f"{score:.4f} — {'НЮ' if is_nude else 'безопасно'}\n"
            ))

        except Exception as e:
            self.image_queue.put(("log", f"Ошибка анализа {img_path}: {e}\n"))

        processed_count += 1
        self.image_queue.put(("status", f"Анализ изображений... ({processed_count} / {total_items})"))
        self.image_queue.put(("progress", processed_count))

    # ✅ Параллельная обработка
    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        future_to_item = {executor.submit(process_item, item): item for item in items}
        for future in as_completed(future_to_item):
            if self.stop_analysis or not self.running:
                break
            result = future.result()
            if result is None:
                continue

            if result[0] == "error":
                _, img_path, e = result
                self.image_queue.put(("log", f"Ошибка анализа {img_path}: {e}\n"))
            else:
                item, img_path, score, is_nude = result
                self.image_queue.put((
                    "update_item", item,
                    {
                        "Порог": f"{score:.4f}",
                        "Статус": "✓" if is_nude else "✗",
                        "tag": "nude" if is_nude else "safe"
                    }
                ))
                self.image_queue.put(
                    ("log", f"{os.path.basename(img_path)}: {score:.4f} — {'НЮ' if is_nude else 'безопасно'}\n"))

            processed_count += 1
            self.image_queue.put(("status", f"Анализ изображений... ({processed_count} / {total_items})"))
            self.image_queue.put(("progress", processed_count))

    # ✅ Итоговый отчёт
    nude_count = sum(1 for f in self.all_files if str(f[6]).strip() == "✓")
    safe_count = sum(1 for f in self.all_files if str(f[6]).strip() == "✗")
    bad_count = sum(1 for f in self.all_files if str(f[6]).strip().upper() == "BAD")
    total = len(self.all_files)

    total_elapsed = (time.time() - start_total)
    report = (
        "\n📊 Результаты анализа\n"
        f"┌──────────────────┬────────────┐\n"
        f"│ Всего            │ {total:<10}│\n"
        f"│ НЮ               │ {nude_count:<10}│\n"
        f"│ Безопасные       │ {safe_count:<10}│\n"
        f"│ BAD              │ {bad_count:<10}│\n"
        f"└──────────────────┴────────────┘\n"
        f"⏱ Общее время анализа: {total_elapsed:.2f} секунд\n"
    )
    self.image_queue.put(("log", report))
    self.image_queue.put(("status", "Анализ завершен"))
    self.image_queue.put(("analysis_complete", ""))

    # ✅ Разблокируем фильтр, порог и модель
    self.filter_combobox.config(state="readonly")  # или state="normal", если так было изначально
    self.threshold_slider.config(state="normal")
    self.model_combobox.config(state="readonly")  # если это Combobox

def analyze_images3(self):
    # 🚫 Блокируем выбор фильтра, порога и модели
    self.filter_combobox.config(state="disabled")
    self.threshold_slider.config(state="disabled")
    self.model_combobox.config(state="disabled")

    threshold = self.threshold_slider.get()
    items = self.result_tree.get_children()
    total_items = len(items)
    processed_count = 0
    max_threads = min(16, get_cpu_cores())

    start_total = time.time()
    log_message(f"▶ Доступно ядер: {get_cpu_cores()} | Используем потоков: {max_threads}\n", self.log_console)

    self.progress["value"] = 0
    self.progress["maximum"] = total_items
    self.progress.update()

    is_mobilenet = "mobilenet" in self.model_type.get().lower()

    def process_item(item):
        nonlocal processed_count
        if self.stop_analysis or not self.running:
            return
        try:
            img_path = self.result_tree.item(item)['values'][2]
            start_time = time.time()
            score, result, bad_flag = is_nude_image(self, img_path, threshold)
            elapsed = (time.time() - start_time) * 1000.0  # мс

            if bad_flag == "BAD":
                self.image_queue.put((
                    "update_item", item,
                    {"Порог": f"{score:.4f}", "Статус": "BAD", "tag": "bad"}
                ))
                self.image_queue.put((
                    "log",
                    f"⏱ Обработка {os.path.basename(img_path)} заняла {elapsed:.1f} ms | BAD\n"
                ))
            else:
                if is_mobilenet:
                    # result = label
                    self.image_queue.put((
                        "update_item", item,
                        {"Порог": f"{score:.4f}", "Статус": result, "tag": "mobilenet"}
                    ))
                    self.image_queue.put((
                        "log",
                        f"⏱ Обработка {os.path.basename(img_path)} заняла {elapsed:.1f} ms | {score:.4f} — {result}\n"
                    ))
                else:
                    # result = is_nude (bool)
                    self.image_queue.put((
                        "update_item", item,
                        {
                            "Порог": f"{score:.4f}",
                            "Статус": "✓" if result else "✗",
                            "tag": "nude" if result else "safe"
                        }
                    ))
                    self.image_queue.put((
                        "log",
                        f"⏱ Обработка {os.path.basename(img_path)} заняла {elapsed:.1f} ms | "
                        f"{score:.4f} — {'НЮ' if result else 'безопасно'}\n"
                    ))
        except Exception as e:
            self.image_queue.put(("log", f"Ошибка анализа {img_path}: {e}\n"))

        processed_count += 1
        self.image_queue.put(("status", f"Анализ изображений... ({processed_count} / {total_items})"))
        self.image_queue.put(("progress", processed_count))

    # ✅ Параллельная обработка
    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        futures = [executor.submit(process_item, item) for item in items]
        for _ in as_completed(futures):
            if self.stop_analysis or not self.running:
                break

    # ✅ Итоговый отчёт
    nude_count = sum(1 for f in self.all_files if str(f[6]).strip() == "✓")
    safe_count = sum(1 for f in self.all_files if str(f[6]).strip() == "✗")
    bad_count = sum(1 for f in self.all_files if str(f[6]).strip().upper() == "BAD")
    # Для MobileNet можно дополнительно собрать список всех label'ов при желании
    total = len(self.all_files)

    total_elapsed = (time.time() - start_total)
    report = (
        "\n📊 Результаты анализа\n"
        f"┌──────────────────┬────────────┐\n"
        f"│ Всего            │ {total:<10}│\n"
        f"│ НЮ               │ {nude_count:<10}│\n"
        f"│ Безопасные       │ {safe_count:<10}│\n"
        f"│ BAD              │ {bad_count:<10}│\n"
        f"└──────────────────┴────────────┘\n"
        f"⏱ Общее время анализа: {total_elapsed:.2f} секунд\n"
    )
    self.image_queue.put(("log", report))
    self.image_queue.put(("status", "Анализ завершен"))
    self.image_queue.put(("analysis_complete", ""))

    # ✅ Разблокируем фильтр, порог и модель
    self.filter_combobox.config(state="readonly")
    self.threshold_slider.config(state="normal")
    self.model_combobox.config(state="readonly")

def analyze_images(self):
    # 🚫 Блокируем выбор фильтра, порога и модели
    self.filter_combobox.config(state="disabled")
    self.threshold_slider.config(state="disabled")
    self.model_combobox.config(state="disabled")

    threshold = self.threshold_slider.get()
    items = self.result_tree.get_children()
    total_items = len(items)
    processed_count = 0
    max_threads = min(16, get_cpu_cores())

    start_total = time.time()
    log_message(f"▶ Доступно ядер: {get_cpu_cores()} | Используем потоков: {max_threads}\n", self.log_console)

    self.progress["value"] = 0
    self.progress["maximum"] = total_items
    self.progress.update()

    model_name = self.model_type.get().lower()
    is_mobilenet = "mobilenet" in model_name
    is_gantman = "gantman" in model_name

    def process_item(item):
        nonlocal processed_count
        if self.stop_analysis or not self.running:
            return
        try:
            img_path = self.result_tree.item(item)['values'][2]
            start_time = time.time()
            score, result, bad_flag = is_nude_image(self, img_path, threshold)
            elapsed = (time.time() - start_time) * 1000.0  # мс

            # BAD файлы
            if bad_flag == "BAD":
                self.image_queue.put((
                    "update_item", item,
                    {"Порог": f"{score:.4f}", "Статус": "BAD", "tag": "bad"}
                ))
                self.image_queue.put((
                    "log",
                    f"⏱ Обработка {os.path.basename(img_path)} заняла {elapsed:.1f} ms | BAD\n"
                ))
            else:
                # MobileNetV2: result — label
                if is_mobilenet:
                    self.image_queue.put((
                        "update_item", item,
                        {"Порог": f"{score:.4f}", "Статус": result, "tag": "mobilenet"}
                    ))
                    self.image_queue.put((
                        "log",
                        f"⏱ Обработка {os.path.basename(img_path)} заняла {elapsed:.1f} ms | {score:.4f} — {result}\n"
                    ))
                # GantMan: result — label (drawings, hentai, neutral, porn, sexy)
                elif is_gantman:
                    self.image_queue.put((
                        "update_item", item,
                        {"Порог": f"{score:.4f}", "Статус": result, "tag": "mobilenet"}  # можно завести свой tag
                    ))
                    self.image_queue.put((
                        "log",
                        f"⏱ Обработка {os.path.basename(img_path)} заняла {elapsed:.1f} ms | {score:.4f} — {result}\n"
                    ))
                # Остальные NSFW модели: result — bool
                else:
                    self.image_queue.put((
                        "update_item", item,
                        {
                            "Порог": f"{score:.4f}",
                            "Статус": "✓" if result else "✗",
                            "tag": "nude" if result else "safe"
                        }
                    ))
                    self.image_queue.put((
                        "log",
                        f"⏱ Обработка {os.path.basename(img_path)} заняла {elapsed:.1f} ms | "
                        f"{score:.4f} — {'НЮ' if result else 'безопасно'}\n"
                    ))

        except Exception as e:
            self.image_queue.put(("log", f"Ошибка анализа {img_path}: {e}\n"))

        processed_count += 1
        self.image_queue.put(("status", f"Анализ изображений... ({processed_count} / {total_items})"))
        self.image_queue.put(("progress", processed_count))

    # ✅ Параллельная обработка
    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        futures = [executor.submit(process_item, item) for item in items]
        for _ in as_completed(futures):
            if self.stop_analysis or not self.running:
                break

    # ✅ Итоговый отчёт
    nude_count = sum(1 for f in self.all_files if str(f[6]).strip() == "✓")
    safe_count = sum(1 for f in self.all_files if str(f[6]).strip() == "✗")
    bad_count = sum(1 for f in self.all_files if str(f[6]).strip().upper() == "BAD")
    total = len(self.all_files)

    total_elapsed = (time.time() - start_total)
    report = (
        "\n📊 Результаты анализа\n"
        f"┌──────────────────┬────────────┐\n"
        f"│ Всего            │ {total:<10}│\n"
        f"│ НЮ               │ {nude_count:<10}│\n"
        f"│ Безопасные       │ {safe_count:<10}│\n"
        f"│ BAD              │ {bad_count:<10}│\n"
        f"└──────────────────┴────────────┘\n"
        f"⏱ Общее время анализа: {total_elapsed:.2f} секунд\n"
    )
    self.image_queue.put(("log", report))
    self.image_queue.put(("status", "Анализ завершен"))
    self.image_queue.put(("analysis_complete", ""))

    # ✅ Разблокируем фильтр, порог и модель
    self.filter_combobox.config(state="readonly")
    self.threshold_slider.config(state="normal")
    self.model_combobox.config(state="readonly")



# ---------------------- ИНИЦИАЛИЗАЦИЯ МОДЕЛЕЙ ----------------------
def initialize_model(self):
    """Инициализирует выбранную модель"""
    # ✅ Очистка предыдущей модели
    self.model = None
    self.predict_fn = None
    self.model_name = self.model_type.get().lower()

    log_message(f"Инициализация модели: {self.model_name}\n", self.log_console)

    try:
        if "yahoo" in self.model_name:
            import opennsfw2
            self.model = opennsfw2
            self.predict_fn = lambda path: float(self.model.predict_image(path))
            log_message("[Yahoo] ✅ Модель готова к работе\n", self.log_console)

        elif "mobilenet" in self.model_name:
            from tensorflow.keras.applications.mobilenet_v2 import preprocess_input
            log_message("[MobileNetV2] Загрузка модели...\n", self.log_console)
            self.model = tf.keras.applications.MobileNetV2(weights='imagenet')
            self.preprocess_input = preprocess_input

            def mobilenet_predict2(img_path):
                img = tf.io.read_file(img_path)
                img = tf.image.decode_jpeg(img, channels=3)
                img = tf.image.resize(img, [224, 224])
                img = self.preprocess_input(img)
                img = tf.expand_dims(img, axis=0)
                predictions = self.model.predict(img)
                return float(predictions[0][0])

            def mobilenet_predict(img_path):
                img = tf.io.read_file(img_path)
                img = tf.image.decode_jpeg(img, channels=3)
                img = tf.image.resize(img, [224, 224])
                img = self.preprocess_input(img)
                img = tf.expand_dims(img, axis=0)
                predictions = self.model.predict(img)
                decoded = decode_predictions(predictions, top=1)[0]  # берём только топ‑1
                top_id, label, prob = decoded[0]
                # возвращаем label и вероятность
                return label, float(prob)


            self.predict_fn = mobilenet_predict
            log_message("[MobileNetV2] ✅ Модель готова к работе\n", self.log_console)

        elif "nsfw hub" in self.model_name:
            import tensorflow_hub as hub
            log_message("[NSFW Hub] Загрузка модели...\n", self.log_console)
            self.model = hub.load("https://tfhub.dev/GourmetAI/nsfw_classifier/1")

            def nsfw_hub_predict(img_path):
                img = tf.io.read_file(img_path)
                img = tf.image.decode_jpeg(img, channels=3)
                img = tf.image.resize(img, [224, 224])
                img = tf.cast(img, tf.float32) / 255.0
                img = tf.expand_dims(img, axis=0)
                preds = self.model(img).numpy()[0]
                return max(preds[1], preds[3], preds[4])

            self.predict_fn = nsfw_hub_predict
            log_message("[NSFW Hub] ✅ Модель готова к работе\n", self.log_console)

        elif "gantman" in self.model_name:
            log_message("[GantMan] Инициализация...\n", self.log_console)
            initialize_model_gantman(self)

        elif "tf hub" in self.model_name:
            import tensorflow_hub as hub
            if not hasattr(self, 'model') or self.model is None:
                log_message("[TF Hub] Загрузка модели...\n", self.log_console)
                self.model = hub.load("https://tfhub.dev/google/openimages/v4/ssd/mobilenetv2/classification/4")

            def tfhub_predict(img_path):
                img = tf.io.read_file(img_path)
                img = tf.image.decode_jpeg(img, channels=3)
                img = tf.image.resize(img, [224, 224])
                img = tf.expand_dims(img, axis=0)
                return float(self.model(img).numpy()[0][1])

            self.predict_fn = tfhub_predict
            log_message("[TF Hub] ✅ Модель готова к работе\n", self.log_console)

        else:
            log_message(f"❌ Неизвестная модель: {self.model_name}\n", self.log_console)
            self.model = None
            self.predict_fn = None

    except Exception as e:
        log_message(f"❌ Ошибка инициализации модели: {str(e)}\n", self.log_console)
        raise


def initialize_model_gantman(self):
    """Скачивает и инициализирует GantMan NSFW модель"""
    model_dir = "nsfw_model_mobilenet_v2"
    saved_model_path = os.path.join(model_dir, "mobilenet_v2_140_224")
    zip_path = "nsfw_model.zip"

    if not hasattr(self, "model_lock"):
        self.model_lock = threading.Lock()

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
        self.predict_fn = lambda path: predict_gantman(self, path)
        log_message("✅ [GantMan] Модель готова к работе\n", self.log_console)


# ---------------------- PREDICT ФУНКЦИИ ----------------------
def predict_gantman2(self, img_path: str) -> float:
    img = tf.io.read_file(img_path)
    img = tf.image.decode_jpeg(img, channels=3)
    img = tf.image.resize(img, [224, 224])
    img = tf.cast(img, tf.float32) / 255.0
    img = tf.expand_dims(img, 0)
    outputs = self.model(img)
    if isinstance(outputs, dict):
        scores = list(outputs.values())[0].numpy()[0]
    else:
        scores = outputs.numpy()[0]
    return float(max(scores[1], scores[3], scores[4]))

import numpy as np

def predict_gantman(self, img_path: str):
    img = tf.io.read_file(img_path)
    img = tf.image.decode_jpeg(img, channels=3)
    img = tf.image.resize(img, [224, 224])
    img = tf.cast(img, tf.float32) / 255.0
    img = tf.expand_dims(img, 0)

    outputs = self.model(img)
    if isinstance(outputs, dict):
        scores = list(outputs.values())[0].numpy()[0]
    else:
        scores = outputs.numpy()[0]

    labels = ["drawings", "hentai", "neutral", "porn", "sexy"]
    best_idx = int(np.argmax(scores))
    best_label = labels[best_idx]
    best_score = float(scores[best_idx])

    return best_score, best_label


# ---------------------- ОСНОВНОЙ ВЫЗОВ ----------------------
def is_nude_image2(self, img_path: str, threshold: float):
    try:
        current_name = self.model_type.get().lower()

        if not hasattr(self, 'predict_fn') or self.predict_fn is None:
            self.initialize_model()

        try:
            if "gantman" in current_name:
                if self.model is None:
                    self.initialize_model()
                score = predict_gantman(self, img_path)
            else:
                score = self.predict_fn(img_path)

            # если дошли сюда — анализ успешен
            return score, score >= threshold, None  # третий флаг — не BAD

        except OSError as ose:
            log_message(f"[SKIP] Поврежденный файл {img_path}: {ose}\n", self.log_console)
            return 0.0, False, "BAD"
        except Exception as inner_e:
            log_message(f"[SKIP] Ошибка обработки {img_path}: {inner_e}\n", self.log_console)
            return 0.0, False, "BAD"

    except Exception as e:
        log_message(f"❌ Ошибка анализа {img_path}: {str(e)}\n", self.log_console)
        import traceback
        traceback.print_exc()
        return 0.0, False, "BAD"


def is_nude_image3(self, img_path: str, threshold: float):
    try:
        current_name = self.model_type.get().lower()

        if not hasattr(self, 'predict_fn') or self.predict_fn is None:
            self.initialize_model()

        # GantMan и прочие NSFW модели:
        if "gantman" in current_name or "yahoo" in current_name or "nsfw" in current_name or "hub" in current_name:
            score = self.predict_fn(img_path)
            return score, score >= threshold, None

        # MobileNetV2: возвращаем тег и вероятность
        if "mobilenet" in current_name:
            label, prob = self.predict_fn(img_path)
            # для совместимости возвращаем:
            return prob, label, None  # второй элемент – будет строка (label)

    except OSError as ose:
        log_message(f"[SKIP] Поврежденный файл {img_path}: {ose}\n", self.log_console)
        return 0.0, "BAD", "BAD"
    except Exception as e:
        log_message(f"[SKIP] Ошибка обработки {img_path}: {e}\n", self.log_console)
        return 0.0, "BAD", "BAD"

def is_nude_image(self, img_path: str, threshold: float):
    try:
        current_name = self.model_type.get().lower()

        if not hasattr(self, 'predict_fn') or self.predict_fn is None:
            self.initialize_model()

        # GantMan
        if "gantman" in current_name:
            if self.model is None:
                self.initialize_model()
            score, label = predict_gantman(self, img_path)
            return score, label, None  # вернем тег вместо true/false

        # MobileNetV2
        if "mobilenet" in current_name:
            label, prob = self.predict_fn(img_path)
            return prob, label, None

        # Остальные NSFW модели (Yahoo, NSFW Hub и др.)
        score = self.predict_fn(img_path)
        return score, score >= threshold, None

    except OSError as ose:
        log_message(f"[SKIP] Поврежденный файл {img_path}: {ose}\n", self.log_console)
        return 0.0, "BAD", "BAD"
    except Exception as e:
        log_message(f"[SKIP] Ошибка обработки {img_path}: {e}\n", self.log_console)
        return 0.0, "BAD", "BAD"

