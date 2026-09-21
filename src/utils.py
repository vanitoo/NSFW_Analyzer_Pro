from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path
from typing import Any

LOG_PATH = Path("analyzer_nu.log")


def convert_size(size_bytes: int) -> str:
    """Convert bytes to a compact human-readable binary size."""
    size = float(size_bytes)
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} ТБ"


def get_cpu_cores() -> int:
    """Return a conservative positive CPU count."""
    return max(1, os.cpu_count() or 4)


def log_message(message: str, console: Any | None = None) -> None:
    """Write a message to the optional Tk console and the persistent log file.

    The console argument must only be used from the Tk main thread.
    """
    if console is not None:
        console.insert(tk.END, message)
        console.see(tk.END)

    try:
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(message)
    except OSError as exc:
        print(f"[Ошибка записи в лог-файл] {exc}")

    print(message.rstrip())
