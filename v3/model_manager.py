import os
import zipfile
import shutil
import urllib.request
import tensorflow as tf
import keras
from utils import log_message
import threading
from PIL import Image

class ModelManager:
    def __init__(self, log_console=None):
        self.log_console = log_console
        self.model = None
        self.predict_fn = None
        self.model_name = ""
        self.model_lock = threading.Lock()

    def set_model(self, model_name: str):
        """Смена модели с полной очисткой и инициализацией"""
        self.model_name = model_name.lower()
        self.model = None
        self.predict_fn = None

        log_message(f"Инициализация модели: {self.model_name}\n", self.log_console)

        if "yahoo" in self.model_name:
            self._init_yahoo()
        elif "mobilenet" in self.model_name:
            self._init_mobilenet()
        elif "nsfw hub" in self.model_name:
            self._init_nsfw_hub()
        elif "gantman" in self.model_name:
            self._init_gantman()
        elif "tf hub" in self.model_name:
            self._init_tfhub()
        else:
            log_message(f"❌ Неизвестная модель: {self.model_name}\n", self.log_console)

    def predict(self, img_path: str) -> float:
        if not self.predict_fn:
            raise RuntimeError("Модель не инициализирована")
        return self.predict_fn(img_path)

    # ================= ИНИЦИАЛИЗАЦИИ =================
    def _init_yahoo(self):
        import opennsfw2
        self.model = opennsfw2
        self.predict_fn = lambda path: float(self.model.predict_image(path))
        log_message("[Yahoo] ✅ Модель готова к работе\n", self.log_console)

    def _init_mobilenet(self):
        from tensorflow.keras.applications.mobilenet_v2 import preprocess_input
        log_message("[MobileNetV2] Загрузка модели...\n", self.log_console)
        self.model = tf.keras.applications.MobileNetV2(weights='imagenet')
        self.predict_fn = lambda path: self._predict_mobilenet(path, preprocess_input)
        log_message("[MobileNetV2] ✅ Модель готова к работе\n", self.log_console)

    def _predict_mobilenet(self, img_path, preprocess_input):
        img = tf.io.read_file(img_path)
        img = tf.image.decode_jpeg(img, channels=3)
        img = tf.image.resize(img, [224, 224])
        img = preprocess_input(img)
        img = tf.expand_dims(img, axis=0)
        predictions = self.model.predict(img)
        return float(predictions[0][0])

    def _init_nsfw_hub(self):
        import tensorflow_hub as hub
        log_message("[NSFW Hub] Загрузка модели...\n", self.log_console)
        self.model = hub.load("https://tfhub.dev/GourmetAI/nsfw_classifier/1")
        def _predict(path):
            img = tf.io.read_file(path)
            img = tf.image.decode_jpeg(img, channels=3)
            img = tf.image.resize(img, [224, 224])
            img = tf.cast(img, tf.float32) / 255.0
            img = tf.expand_dims(img, axis=0)
            preds = self.model(img).numpy()[0]
            return max(preds[1], preds[3], preds[4])
        self.predict_fn = _predict
        log_message("[NSFW Hub] ✅ Модель готова к работе\n", self.log_console)

    def _init_gantman(self):
        model_dir = "nsfw_model_mobilenet_v2"
        saved_model_path = os.path.join(model_dir, "mobilenet_v2_140_224")
        zip_path = "nsfw_model.zip"

        with self.model_lock:
            if not os.path.exists(saved_model_path):
                os.makedirs(model_dir, exist_ok=True)
                if not os.path.exists(zip_path):
                    log_message("[GantMan] Скачиваем NSFW модель...\n", self.log_console)
                    urllib.request.urlretrieve(
                        "https://github.com/GantMan/nsfw_model/archive/refs/heads/master.zip",
                        zip_path
                    )
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

    def _predict_gantman(self, img_path: str) -> float:
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

    def _init_tfhub(self):
        import tensorflow_hub as hub
        log_message("[TF Hub] Загрузка модели...\n", self.log_console)
        self.model = hub.load("https://tfhub.dev/google/openimages/v4/ssd/mobilenetv2/classification/4")
        def _predict(path):
            img = tf.io.read_file(path)
            img = tf.image.decode_jpeg(img, channels=3)
            img = tf.image.resize(img, [224, 224])
            img = tf.expand_dims(img, axis=0)
            return float(self.model(img).numpy()[0][1])
        self.predict_fn = _predict
        log_message("[TF Hub] ✅ Модель готова к работе\n", self.log_console)
