from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path


def emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", required=True)
    args = parser.parse_args()
    checkpoint = Path(args.checkpoint)

    try:
        with contextlib.redirect_stdout(sys.stderr):
            import torch
            from PIL import Image
            from ram import get_transform
            from ram import inference_ram as inference
            from ram.models import ram_plus

            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            transform = get_transform(image_size=384)
            model = ram_plus(
                pretrained=str(checkpoint),
                image_size=384,
                vit="swin_l",
            )
            model.eval()
            model = model.to(device)

        device_label = (
            f"CUDA: {torch.cuda.get_device_name(0)}"
            if device.type == "cuda"
            else "CPU"
        )
        emit({"event": "ready", "device": device_label})
    except Exception as exc:
        emit({"event": "error", "error": f"{type(exc).__name__}: {exc}"})
        return 1

    for line in sys.stdin:
        try:
            request = json.loads(line)
            if request.get("command") == "shutdown":
                break

            image_path = str(request["path"])
            with contextlib.redirect_stdout(sys.stderr), torch.inference_mode():
                image = transform(Image.open(image_path).convert("RGB")).unsqueeze(0).to(device)
                result = inference(image, model)

            emit(
                {
                    "event": "result",
                    "tags": result[0],
                    "tags_zh": result[1],
                }
            )
        except Exception as exc:
            emit({"event": "error", "error": f"{type(exc).__name__}: {exc}"})

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
