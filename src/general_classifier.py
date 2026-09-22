from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from typing import Callable

from PIL import Image

from .general_categories import GENERAL_CATEGORIES
from .paths import OPENCLIP_CACHE_DIR

MODEL_NAME = "MobileCLIP2-S0"
PRETRAINED_NAME = "dfndr2b"
MODEL_REPO = "timm/MobileCLIP2-S0-OpenCLIP"
class GeneralImageClassifier:
    def __init__(self, log: Callable[[str], None]) -> None:
        self.log = log
        self.model = None
        self.preprocess = None
        self.tokenizer = None
        self.text_features = None
        self.torch = None
        self.device = None
        self.device_name = "CPU"

    def load(self) -> None:
        if self.model is not None:
            return

        try:
            import open_clip
            import torch
        except ImportError as exc:
            raise RuntimeError(
                "Для общего классификатора нужен OpenCLIP. "
                "Запустите START.cmd / START_NVIDIA.cmd в экспериментальной ветке "
                "или выполните: pip install -r requirements-general.txt"
            ) from exc

        OPENCLIP_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        before = self._cache_size()

        self.device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
        if self.device.type == "cuda":
            self.device_name = f"CUDA: {torch.cuda.get_device_name(0)}"
        else:
            self.device_name = "CPU"

        self.log(
            f"[General] MobileCLIP2-S0: подготовка модели | устройство: {self.device_name}\n"
        )
        if before:
            self.log(f"[General] локальный cache найден: {before / 1024 / 1024:.1f} MB\n")
        else:
            self.log(
                "[General] cache модели не найден. OpenCLIP скачает MobileCLIP2-S0 "
                "(около 300 MB весов) в cache проекта.\n"
            )

        model, _, preprocess = open_clip.create_model_and_transforms(
            MODEL_NAME,
            pretrained=PRETRAINED_NAME,
            cache_dir=str(OPENCLIP_CACHE_DIR),
        )
        tokenizer = open_clip.get_tokenizer(MODEL_NAME)

        model = model.eval().to(self.device)
        prompts = [item.prompt for item in GENERAL_CATEGORIES]
        text_tokens = tokenizer(prompts).to(self.device)

        with torch.inference_mode():
            text_features = model.encode_text(text_tokens)
            text_features = text_features / text_features.norm(dim=-1, keepdim=True)

        self.model = model
        self.preprocess = preprocess
        self.tokenizer = tokenizer
        self.text_features = text_features
        self.torch = torch

        after = self._cache_size()
        self.log(
            f"[General] MobileCLIP2-S0 готова | cache: {after / 1024 / 1024:.1f} MB "
            f"| {self.device_name}\n"
        )

    def classify(self, image_path: str) -> dict[str, str | float]:
        self.load()
        assert self.model is not None
        assert self.preprocess is not None
        assert self.text_features is not None
        assert self.torch is not None
        assert self.device is not None

        with Image.open(image_path) as image:
            image_tensor = self.preprocess(image.convert("RGB")).unsqueeze(0).to(self.device)

        autocast_context = (
            self.torch.autocast(device_type="cuda", dtype=self.torch.float16)
            if self.device.type == "cuda"
            else nullcontext()
        )
        with self.torch.inference_mode(), autocast_context:
            image_features = self.model.encode_image(image_tensor)
            image_features = image_features / image_features.norm(dim=-1, keepdim=True)
            probabilities = (100.0 * image_features @ self.text_features.T).softmax(dim=-1)[0]

        top_count = min(5, probabilities.numel())
        values, indices = probabilities.topk(top_count)
        top = [
            (GENERAL_CATEGORIES[int(index)], float(value))
            for value, index in zip(values.detach().cpu(), indices.detach().cpu())
        ]

        best, score = top[0]
        tags = ", ".join(f"{item.subcategory} {prob * 100:.1f}%" for item, prob in top)
        return {
            "kind": best.kind,
            "category": best.category,
            "subcategory": best.subcategory,
            "score": score,
            "tags": tags,
        }

    @staticmethod
    def cache_dir() -> Path:
        return OPENCLIP_CACHE_DIR

    def _cache_size(self) -> int:
        if not OPENCLIP_CACHE_DIR.exists():
            return 0
        total = 0
        try:
            for path in OPENCLIP_CACHE_DIR.rglob("*"):
                if path.is_file():
                    total += path.stat().st_size
        except OSError:
            pass
        return total
