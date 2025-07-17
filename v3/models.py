# models.py
import tensorflow as tf
import opennsfw2
import urllib.request, zipfile, shutil, os
import keras
import tensorflow_hub as hub

# ------------------ Base Class ------------------
class BaseNSFWModel:
    def load(self):
        raise NotImplementedError

    def predict(self, img_path: str) -> float:
        raise NotImplementedError

# ------------------ Yahoo Model ------------------
class YahooModel(BaseNSFWModel):
    def load(self):
        self.model = opennsfw2

    def predict(self, img_path: str) -> float:
        return float(self.model.predict_image(img_path))

# ------------------ Gantman Model ------------------
class GantmanModel(BaseNSFWModel):
    def load(self):
        model_dir = "nsfw_model_mobilenet_v2"
        saved_model_path = os.path.join(model_dir, "mobilenet_v2_140_224")
        zip_path = "nsfw_model.zip"

        if not os.path.exists(saved_model_path):
            os.makedirs(model_dir, exist_ok=True)
            if not os.path.exists(zip_path):
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

        self.model = keras.layers.TFSMLayer(saved_model_path, call_endpoint='serving_default')

    def predict(self, img_path: str) -> float:
        img = tf.io.read_file(img_path)
        img = tf.image.decode_jpeg(img, channels=3)
        img = tf.image.resize(img, [224, 224])
        img = tf.cast(img, tf.float32) / 255.0
        img = tf.expand_dims(img, 0)
        outputs = self.model(img)
        scores = list(outputs.values())[0].numpy()[0] if isinstance(outputs, dict) else outputs.numpy()[0]
        return float(max(scores[1], scores[3], scores[4]))

# ------------------ MobileNet Model ------------------
class MobileNetModel(BaseNSFWModel):
    def load(self):
        from tensorflow.keras.applications.mobilenet_v2 import preprocess_input
        self.model = tf.keras.applications.MobileNetV2(weights='imagenet')
        self.preprocess_input = preprocess_input

    def predict(self, img_path: str) -> float:
        img = tf.io.read_file(img_path)
        img = tf.image.decode_jpeg(img, channels=3)
        img = tf.image.resize(img, [224, 224])
        img = self.preprocess_input(img)
        img = tf.expand_dims(img, axis=0)
        predictions = self.model.predict(img)
        return float(predictions[0][0])

# ------------------ NSFW Hub Model ------------------
class NsfwHubModel(BaseNSFWModel):
    def load(self):
        self.model = hub.load("https://tfhub.dev/GourmetAI/nsfw_classifier/1")

    def predict(self, img_path: str) -> float:
        img = tf.io.read_file(img_path)
        img = tf.image.decode_jpeg(img, channels=3)
        img = tf.image.resize(img, [224, 224])
        img = tf.cast(img, tf.float32) / 255.0
        img = tf.expand_dims(img, axis=0)
        preds = self.model(img).numpy()[0]
        return float(max(preds[1], preds[3], preds[4]))

# ------------------ TF Hub Model ------------------
class TfHubModel(BaseNSFWModel):
    def load(self):
        self.model = hub.load("https://tfhub.dev/google/openimages/v4/ssd/mobilenetv2/classification/4")

    def predict(self, img_path: str) -> float:
        img = tf.io.read_file(img_path)
        img = tf.image.decode_jpeg(img, channels=3)
        img = tf.image.resize(img, [224, 224])
        img = tf.expand_dims(img, axis=0)
        return float(self.model(img).numpy()[0][1])


# analyzer.py (переписанные части)
from models import YahooModel, GantmanModel, MobileNetModel, NsfwHubModel, TfHubModel

def initialize_model(self):
    self.current_model = None
    model_name = self.model_type.get().lower()
    try:
        if "yahoo" in model_name:
            self.current_model = YahooModel()
        elif "gantman" in model_name:
            self.current_model = GantmanModel()
        elif "mobilenet" in model_name:
            self.current_model = MobileNetModel()
        elif "nsfw hub" in model_name:
            self.current_model = NsfwHubModel()
        elif "tf hub" in model_name:
            self.current_model = TfHubModel()
        else:
            log_message(f"❌ Неизвестная модель: {model_name}\n", self.log_console)
            return
        self.current_model.load()
        log_message(f"✅ [{model_name}] Модель готова к работе\n", self.log_console)
    except Exception as e:
        log_message(f"❌ Ошибка инициализации модели: {str(e)}\n", self.log_console)
        import traceback
        traceback.print_exc()
        self.current_model = None

def is_nude_image(self, img_path: str, threshold: float):
    if self.current_model is None:
        log_message("❌ Модель не инициализирована!\n", self.log_console)
        return 0.0, False
    try:
        start_time = time.time()
        score = self.current_model.predict(img_path)
        elapsed = (time.time() - start_time) * 1000.0
        log_message(f"⏱ Обработка {os.path.basename(img_path)} заняла {elapsed:.1f} ms | {score:.4f}\n", self.log_console)
        return score, score >= threshold
    except Exception as e:
        log_message(f"❌ Ошибка анализа {img_path}: {str(e)}\n", self.log_console)
        import traceback
        traceback.print_exc()
        return 0.0, False
