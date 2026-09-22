from __future__ import annotations

import datetime as dt
import os
from pathlib import Path
from typing import Any

from .utils import convert_size

SUPPORTED_FORMATS = {".png", ".jpg", ".jpeg", ".bmp", ".gif"}
IGNORED_OUTPUT_DIRS = {"NU", "BAD", "UNKNOWN"}


def _iter_images(folder_path: str):
    base = Path(folder_path)
    for root, dirs, files in os.walk(base):
        dirs[:] = [name for name in dirs if name.upper() not in IGNORED_OUTPUT_DIRS]
        root_path = Path(root)
        for filename in files:
            if Path(filename).suffix.lower() in SUPPORTED_FORMATS:
                yield root_path / filename


def scan_folder_async(self: Any, folder_path: str) -> None:
    """Collect image metadata in a worker thread and send batches to Tk via Queue."""
    paths = list(_iter_images(folder_path))
    total_files = len(paths)
    self.image_queue.put(("scan_start", total_files))

    batch: list[tuple] = []
    processed_count = 0

    for img_path in paths:
        if self.stop_analysis or not self.running:
            self.image_queue.put(("scan_cancelled", processed_count))
            return

        try:
            stat = img_path.stat()
            processed_count += 1
            batch.append(
                (
                    processed_count,
                    img_path.name,
                    str(img_path),
                    convert_size(stat.st_size),
                    dt.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                    "",
                    "",
                    "",
                )
            )
            if len(batch) >= 100:
                self.image_queue.put(("scan_batch", batch))
                batch = []
            if processed_count % 100 == 0 or processed_count == total_files:
                self.image_queue.put(("progress", processed_count))
                self.image_queue.put(("status", f"Сканирование... ({processed_count}/{total_files})"))
        except OSError as exc:
            self.image_queue.put(("log", f"Ошибка чтения {img_path}: {exc}\n"))

    if batch:
        self.image_queue.put(("scan_batch", batch))

    self.image_queue.put(("scan_complete", processed_count))
