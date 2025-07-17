import datetime
import os
import tkinter as tk

from utils import convert_size, log_message


def scan_folder_async2(self, folder_path):
    """Асинхронное сканирование папки"""
    self.status_var.set("Сканирование...")
    self.progress.start()
    self.analyze_button.config(state=tk.DISABLED)

    supported_formats = ('.png', '.jpg', '.jpeg', '.bmp', '.gif')
    file_count = 0
    batch = []

    for root, _, files in os.walk(folder_path):
        for file in files:
            if self.stop_analysis:
                log_message("⛔ Сканирование прервано пользователем\n")
                return
            if file.lower().endswith(supported_formats):
                file_count += 1
                img_path = os.path.join(root, file)

                # Получаем метаданные
                try:
                    stat = os.stat(img_path)
                    size = convert_size(stat.st_size)
                    mtime = datetime.datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M')
                    batch.append((file_count, os.path.basename(img_path), img_path, size, mtime, "", ""))

                    # Пакетное обновление каждые 100 файлов
                    if len(batch) >= 100:
                        self.update_file_list(batch)
                        batch = []

                except Exception as e:
                    self.image_queue.put(("log", f"Ошибка обработки {img_path}: {e}\n"))

    # Добавляем оставшиеся файлы
    if batch:
        self.update_file_list(batch)

    self.image_queue.put(("scan_complete", file_count))
    # self.status_var.set(f"Загружено {file_count} изображений")


def scan_folder_async(self, folder_path):
    """Асинхронное сканирование папки с прогресс-баром"""

    # Сначала считаем общее количество файлов
    supported_formats = ('.png', '.jpg', '.jpeg', '.bmp', '.gif')
    all_files = []
    for root, _, files in os.walk(folder_path):
        for file in files:
            if file.lower().endswith(supported_formats):
                all_files.append(os.path.join(root, file))
    total_files = len(all_files)

    self.progress.stop()
    self.progress["value"] = 0
    self.progress["maximum"] = total_files
    self.status_var.set("Сканирование...")
    self.analyze_button.config(state=tk.DISABLED)

    batch = []
    processed_count = 0

    for img_path in all_files:
        if self.stop_analysis:
            log_message("⛔ Сканирование прервано пользователем\n")
            return

        try:
            stat = os.stat(img_path)
            size = convert_size(stat.st_size)
            mtime = datetime.datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M')
            processed_count += 1
            batch.append((processed_count, os.path.basename(img_path), img_path, size, mtime, "", ""))

            # # обновляем прогресс
            # self.progress["value"] = processed_count
            # self.status_var.set(f"Сканирование... ({processed_count}/{total_files})")

            if len(batch) >= 100:
                self.update_file_list(batch)
                batch = []
                # обновляем прогресс
                self.progress["value"] = processed_count
                self.status_var.set(f"Сканирование... ({processed_count}/{total_files})")


        except Exception as e:
            self.image_queue.put(("log", f"Ошибка обработки {img_path}: {e}\n"))

    if batch:
        self.update_file_list(batch)

    self.progress["value"] = total_files
    self.status_var.set(f"Загружено {processed_count} изображений")
    self.analyze_button.config(state=tk.NORMAL)


def update_file_list(self, batch):
    """Сохраняет и отображает список файлов"""
    self.all_files.extend(batch)  # Сохраняем в память

    self.root.after(0, lambda: [
        self.result_tree.insert("", "end", values=item) for item in batch
    ])
