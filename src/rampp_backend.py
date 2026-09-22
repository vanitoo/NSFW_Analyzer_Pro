from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable, TextIO

from .paths import PROJECT_ROOT, RAMPP_CACHE_DIR

RAMPP_REPO_ID = "xinyu1205/recognize-anything-plus-model"
RAMPP_CHECKPOINT = "ram_plus_swin_large_14m.pth"


class RAMPlusPlusBackend:
    def __init__(self, log: Callable[[str], None]) -> None:
        self.log = log
        self.process: subprocess.Popen[str] | None = None
        self._stderr_thread: threading.Thread | None = None
        self.device_name = "не загружен"

    def _runtime_python(self) -> Path:
        override = os.getenv("NSFW_ANALYZER_RAMPP_PYTHON")
        if override:
            python_path = Path(os.path.expandvars(os.path.expanduser(override))).resolve()
            if not python_path.exists():
                raise RuntimeError(
                    "NSFW_ANALYZER_RAMPP_PYTHON указывает на несуществующий файл: "
                    f"{python_path}"
                )
            return python_path

        if sys.platform.startswith("win"):
            python_path = PROJECT_ROOT / ".venv-rampp" / "Scripts" / "python.exe"
        else:
            python_path = PROJECT_ROOT / ".venv-rampp" / "bin" / "python"
        if not python_path.exists():
            raise RuntimeError(
                "RAM++ использует отдельное окружение из-за конфликта старого timm с OpenCLIP. "
                "На Windows запустите SETUP_RAMPP.cmd или задайте "
                "NSFW_ANALYZER_RAMPP_PYTHON на Python готового RAM++ окружения."
            )
        return python_path

    def _ensure_checkpoint(self) -> Path:
        try:
            from huggingface_hub import snapshot_download
            from tqdm.auto import tqdm
        except ImportError as exc:
            raise RuntimeError(
                "Для загрузки RAM++ нужен huggingface_hub. "
                "Запустите START.cmd / START_NVIDIA.cmd."
            ) from exc

        RAMPP_CACHE_DIR.mkdir(parents=True, exist_ok=True)

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
                        self.log(f"[RAM++] загрузка checkpoint: {percent}%\n")
                        progress_self._last_logged_percent = percent
                return result

        try:
            snapshot = snapshot_download(
                repo_id=RAMPP_REPO_ID,
                cache_dir=str(RAMPP_CACHE_DIR),
                allow_patterns=(RAMPP_CHECKPOINT,),
                local_files_only=True,
            )
        except Exception:
            self.log(
                "[RAM++] checkpoint не найден. Скачиваем официальный "
                "ram_plus_swin_large_14m.pth (~3 GB)...\n"
            )
            snapshot = snapshot_download(
                repo_id=RAMPP_REPO_ID,
                cache_dir=str(RAMPP_CACHE_DIR),
                allow_patterns=(RAMPP_CHECKPOINT,),
                tqdm_class=LogTqdm,
            )

        checkpoint = Path(snapshot) / RAMPP_CHECKPOINT
        if not checkpoint.exists():
            raise RuntimeError(f"RAM++ checkpoint не найден после загрузки: {checkpoint}")
        return checkpoint

    def _drain_stderr(self, stream: TextIO) -> None:
        try:
            for line in stream:
                if line.strip():
                    self.log(f"[RAM++] {line}")
        except Exception:
            pass

    def load(self) -> None:
        if self.process is not None and self.process.poll() is None:
            return

        python_path = self._runtime_python()
        checkpoint = self._ensure_checkpoint()
        worker_path = PROJECT_ROOT / "src" / "rampp_worker.py"

        self.log("[RAM++] запуск изолированного runtime...\n")
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.process = subprocess.Popen(
            [
                str(python_path),
                str(worker_path),
                "--checkpoint",
                str(checkpoint),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
            creationflags=creationflags,
        )

        assert self.process.stdout is not None
        assert self.process.stderr is not None

        self._stderr_thread = threading.Thread(
            target=self._drain_stderr,
            args=(self.process.stderr,),
            daemon=True,
            name="rampp-stderr",
        )
        self._stderr_thread.start()

        line = self.process.stdout.readline()
        if not line:
            code = self.process.poll()
            self.unload()
            raise RuntimeError(f"RAM++ worker завершился при старте (код {code})")

        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            self.unload()
            raise RuntimeError(f"RAM++ worker вернул некорректный ответ: {line[:200]}") from exc

        if message.get("event") != "ready":
            error = str(message.get("error", message))
            self.unload()
            raise RuntimeError(f"RAM++ не инициализирован: {error}")

        self.device_name = str(message.get("device", "unknown"))
        self.log(f"[RAM++] готов | устройство: {self.device_name}\n")

    def classify(self, image_path: str) -> dict[str, str | float]:
        self.load()
        assert self.process is not None
        assert self.process.stdin is not None
        assert self.process.stdout is not None

        request = json.dumps({"path": image_path}, ensure_ascii=False)
        self.process.stdin.write(request + "\n")
        self.process.stdin.flush()

        line = self.process.stdout.readline()
        if not line:
            code = self.process.poll()
            raise RuntimeError(f"RAM++ worker неожиданно завершился (код {code})")

        response = json.loads(line)
        if response.get("event") == "error":
            raise RuntimeError(str(response.get("error", "неизвестная ошибка RAM++")))

        tags = str(response.get("tags", "")).replace(" | ", ", ")
        return {
            "kind": "Теги",
            "category": "",
            "subcategory": "",
            "score": "",
            "top5": "",
            "tags": tags,
        }

    def unload(self) -> None:
        process = self.process
        self.process = None
        if process is None:
            return
        try:
            if process.stdin is not None:
                process.stdin.write(json.dumps({"command": "shutdown"}) + "\n")
                process.stdin.flush()
        except Exception:
            pass
        try:
            process.terminate()
            process.wait(timeout=5)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass
