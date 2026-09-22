from __future__ import annotations

import gc
from contextlib import nullcontext
from pathlib import Path
from typing import Callable

from PIL import Image

from .general_categories import GENERAL_CATEGORIES
from .paths import OPENCLIP_CACHE_DIR

MODEL_MOBILECLIP_S0 = "MobileCLIP2-S0"
MODEL_MOBILECLIP_S2 = "MobileCLIP2-S2"
MODEL_RAMPP = "RAM++"

GENERAL_MODEL_CHOICES = (
    MODEL_MOBILECLIP_S0,
    MODEL_MOBILECLIP_S2,
    MODEL_RAMPP,
)

MOBILECLIP_VARIANTS = {
    MODEL_MOBILECLIP_S0: {
        "model_name": "MobileCLIP2-S0",
        "pretrained": "dfndr2b",
        "repo_id": "timm/MobileCLIP2-S0-OpenCLIP",
        "size_hint": "~300 MB",
    },
    MODEL_MOBILECLIP_S2: {
        "model_name": "MobileCLIP2-S2",
        "pretrained": "dfndr2b",
        "repo_id": "timm/MobileCLIP2-S2-OpenCLIP",
        "size_hint": "~400 MB",
    },
}


class GeneralImageClassifier:
    def __init__(self, log: Callable[[str], None], variant: str = MODEL_MOBILECLIP_S0) -> None:
        if variant not in MOBILECLIP_VARIANTS:
            raise ValueError(f"Неизвестная MobileCLIP-модель: {variant}")
        self.log = log
        self.variant = variant
        self.config = MOBILECLIP_VARIANTS[variant]
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
            from huggingface_hub import snapshot_download
            from tqdm.auto import tqdm
        except ImportError as exc:
            raise RuntimeError(
                "Для общего классификатора нужен OpenCLIP. "
                "Запустите START.cmd / START_NVIDIA.cmd или выполните: "
                "pip install -r requirements-general.txt"
            ) from exc

        OPENCLIP_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        model_name = str(self.config["model_name"])
        repo_id = str(self.config["repo_id"])
        size_hint = str(self.config["size_hint"])

        class LogTqdm(tqdm):
            def __init__(progress_self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                progress_self._last_logged_percent = -10

            def update(progress_self, n=1):
                result = super().update(n)
                total = progress_self.total or 0
                if total:
                    percent = min(100, int(progress_self.n * 100 / total))
                    if percent >= progress_self._last_logged_percent + 10 or percent == 100:
                        self.log(f"[General] загрузка {model_name}: {percent}%\n")
                        progress_self._last_logged_percent = percent
                return result

        try:
            snapshot_download(
                repo_id=repo_id,
                cache_dir=str(OPENCLIP_CACHE_DIR),
                allow_patterns=("open_clip_model.safetensors",),
                local_files_only=True,
            )
            weights_cached = True
        except Exception:
            weights_cached = False

        if not weights_cached:
            self.log(
                f"[General] cache {model_name} не найден. "
                f"Скачиваем safetensors-веса ({size_hint})...\n"
            )
            snapshot_download(
                repo_id=repo_id,
                cache_dir=str(OPENCLIP_CACHE_DIR),
                allow_patterns=("open_clip_model.safetensors",),
                tqdm_class=LogTqdm,
            )
            self.log(f"[General] загрузка {model_name}: 100% — веса сохранены\n")

        self.device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
        if self.device.type == "cuda":
            self.device_name = f"CUDA: {torch.cuda.get_device_name(0)}"
        else:
            self.device_name = "CPU"

        self.log(f"[General] {model_name}: подготовка | устройство: {self.device_name}\n")
        self.log("[General] инициализация OpenCLIP runtime...\n")

        model, _, preprocess = open_clip.create_model_and_transforms(
            model_name,
            pretrained=str(self.config["pretrained"]),
            cache_dir=str(OPENCLIP_CACHE_DIR),
        )
        tokenizer = open_clip.get_tokenizer(model_name)

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
        self.log(f"[General] {model_name} готова | {self.device_name}\n")

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
        top5 = ", ".join(f"{item.subcategory} {prob * 100:.1f}%" for item, prob in top)
        return {
            "kind": best.kind,
            "category": best.category,
            "subcategory": best.subcategory,
            "score": score,
            "top5": top5,
            "tags": "",
        }

    def unload(self) -> None:
        torch = self.torch
        self.model = None
        self.preprocess = None
        self.tokenizer = None
        self.text_features = None
        self.device = None
        self.torch = None
        gc.collect()
        if torch is not None:
            try:
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass

    @staticmethod
    def cache_dir() -> Path:
        return OPENCLIP_CACHE_DIR


def create_general_backend(name: str, log: Callable[[str], None]):
    if name == MODEL_RAMPP:
        from .rampp_backend import RAMPlusPlusBackend

        return RAMPlusPlusBackend(log)
    if name in MOBILECLIP_VARIANTS:
        return GeneralImageClassifier(log, name)
    raise ValueError(f"Неизвестный backend общего классификатора: {name}")
