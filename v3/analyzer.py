import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from utils import get_cpu_cores, log_message
from model_manager import ModelManager  # ✅ новый модуль

# ================== Воркеры и логика анализа ==================

class AnalyzerWorker:
    def __init__(self, ui_ref):
        self.ui = ui_ref
        self.model_manager = ModelManager(log_console=self.ui.log_console)
        self.stop_analysis = False
        self.running = False
        self.image_queue = self.ui.image_queue
        self.all_files = []
        self.model_type = self.ui.model_type  # combobox var
        self.threshold_slider = self.ui.threshold_slider
        self.result_tree = self.ui.result_tree
        self.progress = self.ui.progress

    def analyze_images(self):
        threshold = self.threshold_slider.get()
        items = self.result_tree.get_children()
        total_items = len(items)
        processed_count = 0
        max_threads = 1  # или min(16, get_cpu_cores())

        start_total = time.time()
        log_message(f"▶ Доступно ядер: {get_cpu_cores()} | Используем потоков: {max_threads}\n", self.ui.log_console)

        self.progress["value"] = 0
        self.progress["maximum"] = total_items
        self.progress.update()

        def process_item(item):
            nonlocal processed_count
            if self.stop_analysis or not self.running:
                return
            try:
                img_path = self.result_tree.item(item)['values'][2]
                score, is_nude = self.is_nude_image(img_path, threshold)
                self.image_queue.put((
                    "update_item", item,
                    {
                        "Порог": f"{score:.4f}",
                        "НЮ": "✓" if is_nude else "✗",
                        "tag": "nude" if is_nude else "safe"
                    }
                ))
                self.image_queue.put(("log", f"{os.path.basename(img_path)}: {score:.4f} — {'НЮ' if is_nude else 'безопасно'}\n"))
            except Exception as e:
                self.image_queue.put(("log", f"Ошибка анализа {img_path}: {e}\n"))

            processed_count += 1
            self.image_queue.put(("status", f"Анализ изображений... ({processed_count} / {total_items})"))
            self.image_queue.put(("progress", processed_count))

        with ThreadPoolExecutor(max_workers=max_threads) as executor:
            for item in items:
                if self.stop_analysis or not self.running:
                    break
                executor.submit(process_item, item)

        nude_count = sum(1 for f in self.all_files if str(f[6]).strip() == "✓")
        safe_count = sum(1 for f in self.all_files if str(f[6]).strip() == "✗")
        total = len(self.all_files)
        total_elapsed = (time.time() - start_total)

        report = (
            "\n📊 Результаты анализа\n"
            f"┌──────────────────┬────────────┐\n"
            f"│ Всего            │ {total:<10}│\n"
            f"│ НЮ               │ {nude_count:<10}│\n"
            f"│ Безопасные       │ {safe_count:<10}│\n"
            f"└──────────────────┴────────────┘\n"
            f"⏱ Общее время анализа: {total_elapsed:.2f} секунд\n"
        )
        self.image_queue.put(("log", report))
        self.image_queue.put(("status", "Анализ завершен"))
        self.image_queue.put(("analysis_complete", ""))

    def is_nude_image(self, img_path: str, threshold: float):
        """Вызов модели для анализа одного изображения"""
        try:
            start_time = time.time()
            current_name = self.model_type.get().lower()

            # если сменили модель, инициализируем её
            if self.model_manager.model_name != current_name:
                self.model_manager.set_model(current_name)

            score = self.model_manager.predict(img_path)

            elapsed = (time.time() - start_time) * 1000.0
            log_message(f"⏱ Обработка {os.path.basename(img_path)} заняла {elapsed:.1f} ms | {score:.4f}\n", self.ui.log_console)

            return score, score >= threshold
        except Exception as e:
            log_message(f"❌ Ошибка анализа {img_path}: {str(e)}\n", self.ui.log_console)
            import traceback
            traceback.print_exc()
            return 0.0, False
