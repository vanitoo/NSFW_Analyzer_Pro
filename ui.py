from __future__ import annotations

import os
import queue
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from PIL import Image, ImageTk

from analyzer import MODEL_CHOICES, analyze_images
from scanner import scan_folder_async
from utils import log_message


class NSFWAnalyzerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("NSFW Analyzer Pro")
        self.root.geometry("1400x800")
        self.root.minsize(980, 620)

        self.running = True
        self.stop_analysis = False
        self.analysis_thread: threading.Thread | None = None
        self.scan_thread: threading.Thread | None = None
        self.image_queue: queue.Queue = queue.Queue()

        self.model = None
        self.model_name: str | None = None
        self.predict_fn = None
        self.model_lock = threading.Lock()

        self.all_files: list[list] = []
        self._last_preview_path: str | None = None

        self._create_widgets()
        self.root.after(100, self.process_queue)
        self.status_var.set("Готов к работе")

    def _create_widgets(self) -> None:
        self.control_frame = tk.Frame(self.root)
        self.control_frame.pack(fill=tk.X, padx=5, pady=5)
        self.control_frame.columnconfigure(1, weight=1)

        tk.Label(self.control_frame, text="Папка:").grid(row=0, column=0, padx=5)
        self.path_entry = tk.Entry(self.control_frame, width=50)
        self.path_entry.grid(row=0, column=1, padx=5, sticky="ew")

        self.browse_button = tk.Button(self.control_frame, text="Обзор", command=self.browse_folder)
        self.browse_button.grid(row=0, column=2, padx=5)

        tk.Label(self.control_frame, text="Порог:").grid(row=0, column=3, padx=5)
        self.threshold_slider = tk.Scale(
            self.control_frame,
            from_=0.1,
            to=1.0,
            resolution=0.01,
            orient=tk.HORIZONTAL,
            length=180,
        )
        self.threshold_slider.set(0.7)
        self.threshold_slider.grid(row=0, column=4, padx=5)

        tk.Label(self.control_frame, text="Фильтр:").grid(row=0, column=5, padx=5)
        self.filter_var = tk.StringVar(value="Все")
        self.filter_combobox = ttk.Combobox(
            self.control_frame,
            textvariable=self.filter_var,
            values=("Все", "Только НЮ", "Только безопасные", "Неопределённые", "BAD"),
            state="readonly",
            width=16,
        )
        self.filter_combobox.grid(row=0, column=6, padx=5)
        self.filter_combobox.bind("<<ComboboxSelected>>", self.apply_filter)

        self.analyze_button = tk.Button(self.control_frame, text="Анализировать", command=self.toggle_analysis)
        self.analyze_button.grid(row=0, column=7, padx=5)

        self.move_button = tk.Button(
            self.control_frame,
            text="Переместить",
            command=self.move_images_by_filter,
            state=tk.DISABLED,
        )
        self.move_button.grid(row=0, column=8, padx=5)

        tk.Label(self.control_frame, text="Модель:").grid(row=0, column=9, padx=5)
        self.model_type = tk.StringVar(value=MODEL_CHOICES[0])
        self.model_combobox = ttk.Combobox(
            self.control_frame,
            textvariable=self.model_type,
            values=MODEL_CHOICES,
            state="readonly",
            width=18,
        )
        self.model_combobox.grid(row=0, column=10, padx=5)

        self.main_paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.main_paned.pack(fill=tk.BOTH, expand=True)

        self.left_paned = tk.PanedWindow(self.main_paned, orient=tk.VERTICAL)
        self.main_paned.add(self.left_paned, width=1000)

        self.tree_frame = tk.Frame(self.left_paned)
        self.left_paned.add(self.tree_frame, height=520)

        self.tree_scroll_y = ttk.Scrollbar(self.tree_frame)
        self.tree_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree_scroll_x = ttk.Scrollbar(self.tree_frame, orient=tk.HORIZONTAL)
        self.tree_scroll_x.pack(side=tk.BOTTOM, fill=tk.X)

        columns = ("#", "Имя файла", "Путь", "Размер", "Дата изменения", "Оценка", "Статус")
        self.result_tree = ttk.Treeview(
            self.tree_frame,
            columns=columns,
            show="headings",
            yscrollcommand=self.tree_scroll_y.set,
            xscrollcommand=self.tree_scroll_x.set,
        )
        self.result_tree.pack(fill=tk.BOTH, expand=True)
        self.tree_scroll_y.config(command=self.result_tree.yview)
        self.tree_scroll_x.config(command=self.result_tree.xview)

        column_config = {
            "#": {"width": 55, "anchor": "center", "stretch": False},
            "Имя файла": {"width": 220},
            "Путь": {"width": 420},
            "Размер": {"width": 90, "anchor": "e"},
            "Дата изменения": {"width": 135},
            "Оценка": {"width": 85, "anchor": "center"},
            "Статус": {"width": 80, "anchor": "center"},
        }
        for column, config in column_config.items():
            self.result_tree.heading(
                column,
                text=column,
                command=lambda current=column: self.sort_treeview_column(current, False),
            )
            self.result_tree.column(column, **config)

        self.result_tree.tag_configure("nude", background="#ffcccc")
        self.result_tree.tag_configure("safe", background="#ccffcc")
        self.result_tree.tag_configure("bad", background="#ffe680")

        self.log_frame = tk.LabelFrame(self.left_paned, text="Лог")
        self.left_paned.add(self.log_frame, height=210)
        self.log_console = scrolledtext.ScrolledText(self.log_frame, height=8)
        self.log_console.pack(fill=tk.BOTH, expand=True)

        self.preview_frame = tk.LabelFrame(self.main_paned, text="Превью")
        self.main_paned.add(self.preview_frame, width=340)
        self.preview_label = tk.Label(self.preview_frame, text="Выберите изображение")
        self.preview_label.pack(fill=tk.BOTH, expand=True)

        status_frame = tk.Frame(self.root, bd=1, relief=tk.SUNKEN)
        status_frame.pack(side=tk.BOTTOM, fill=tk.X)
        self.status_var = tk.StringVar()
        self.status_bar = tk.Label(status_frame, textvariable=self.status_var, anchor="w")
        self.status_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.progress = ttk.Progressbar(status_frame, mode="determinate", length=320, maximum=1)
        self.progress.pack(side=tk.RIGHT, padx=5)

        self.result_tree.bind("<Double-1>", self.open_image)
        self.result_tree.bind("<Return>", self.open_image)
        self.result_tree.bind("<<TreeviewSelect>>", self.show_preview)
        self.root.bind("<F6>", self.move_selected_file_by_filter)
        self.root.bind("<Delete>", self.delete_selected_file)

    def _set_scanning(self, active: bool) -> None:
        state = tk.DISABLED if active else tk.NORMAL
        self.browse_button.config(state=state)
        self.path_entry.config(state=state)
        self.analyze_button.config(state=tk.DISABLED if active else tk.NORMAL)
        self.filter_combobox.config(state="disabled" if active else "readonly")

    def _set_analysis_controls(self, active: bool) -> None:
        self.browse_button.config(state=tk.DISABLED if active else tk.NORMAL)
        self.path_entry.config(state=tk.DISABLED if active else tk.NORMAL)
        self.filter_combobox.config(state="disabled" if active else "readonly")
        self.threshold_slider.config(state=tk.DISABLED if active else tk.NORMAL)
        self.model_combobox.config(state="disabled" if active else "readonly")
        self.analyze_button.config(text="Остановить" if active else "Анализировать", state=tk.NORMAL)
        if not active:
            self.move_button.config(state=tk.NORMAL if self.all_files else tk.DISABLED)

    def browse_folder(self) -> None:
        folder_path = filedialog.askdirectory()
        if not folder_path:
            return

        self.stop_analysis = False
        self.result_tree.delete(*self.result_tree.get_children())
        self.all_files.clear()
        self.preview_label.config(image="", text="Выберите изображение")
        self.preview_label.image = None
        self._last_preview_path = None

        self.path_entry.delete(0, tk.END)
        self.path_entry.insert(0, folder_path)
        self.move_button.config(state=tk.DISABLED)
        self._set_scanning(True)

        self.scan_thread = threading.Thread(
            target=scan_folder_async,
            args=(self, folder_path),
            daemon=True,
            name="folder-scan",
        )
        self.scan_thread.start()

    def toggle_analysis(self) -> None:
        if self.analysis_thread and self.analysis_thread.is_alive():
            self.stop_analysis = True
            self.analyze_button.config(text="Останавливаю...", state=tk.DISABLED)
            return
        self.start_analysis()

    def start_analysis(self) -> None:
        if not self.path_entry.get():
            messagebox.showerror("Ошибка", "Выберите папку для анализа")
            return

        items: list[tuple[str, str]] = []
        for item_id in self.result_tree.get_children():
            values = self.result_tree.item(item_id, "values")
            if len(values) >= 3:
                items.append((item_id, str(values[2])))

        if not items:
            messagebox.showinfo("Анализ", "В текущем списке нет изображений")
            return

        threshold = float(self.threshold_slider.get())
        model_name = self.model_type.get()
        self.stop_analysis = False
        self._set_analysis_controls(True)
        self.progress["value"] = 0
        self.progress["maximum"] = len(items)
        self.status_var.set("Подготовка модели...")

        self.analysis_thread = threading.Thread(
            target=analyze_images,
            args=(self, items, threshold, model_name),
            daemon=True,
            name="image-analysis",
        )
        self.analysis_thread.start()

    def process_queue(self) -> None:
        if not self.running:
            return

        try:
            while True:
                task = self.image_queue.get_nowait()
                event = task[0]

                if event == "log":
                    log_message(task[1], self.log_console)

                elif event == "status":
                    self.status_var.set(task[1])

                elif event in {"scan_start", "progress_setup"}:
                    maximum = max(1, int(task[1]))
                    self.progress["maximum"] = maximum
                    self.progress["value"] = 0
                    if event == "scan_start":
                        self.status_var.set(f"Сканирование... найдено {task[1]} файлов")

                elif event == "scan_batch":
                    for file_data in task[1]:
                        row = list(file_data)
                        self.all_files.append(row)
                        self._insert_row(row)

                elif event == "scan_complete":
                    count = int(task[1])
                    self.progress["value"] = count
                    self.status_var.set(f"Загружено {count} изображений. Готов к анализу")
                    self._set_scanning(False)

                elif event == "scan_cancelled":
                    self.status_var.set(f"Сканирование остановлено ({task[1]} файлов)")
                    self._set_scanning(False)

                elif event == "update_item":
                    self._apply_item_update(task[1], task[2])

                elif event == "progress":
                    self.progress["value"] = int(task[1])

                elif event == "analysis_complete":
                    self._set_analysis_controls(False)
                    self.analysis_thread = None

                elif event == "analysis_error":
                    self._set_analysis_controls(False)
                    self.analysis_thread = None
                    self.status_var.set("Ошибка инициализации модели")
                    messagebox.showerror("Ошибка модели", task[1])

        except queue.Empty:
            pass

        if self.running:
            self.root.after(100, self.process_queue)

    def _insert_row(self, file_data: list | tuple) -> str:
        status = str(file_data[6]).strip() if len(file_data) > 6 else ""
        tag = self._status_tag(status)
        return self.result_tree.insert("", "end", values=file_data, tags=(tag,) if tag else ())

    def _apply_item_update(self, item_id: str, updates: dict[str, str]) -> None:
        if not self.result_tree.exists(item_id):
            return

        values_before = list(self.result_tree.item(item_id, "values"))
        if len(values_before) < 3:
            return
        path = str(values_before[2])

        tag = updates.get("tag")
        for column, value in updates.items():
            if column != "tag":
                self.result_tree.set(item_id, column, value)
        if tag:
            self.result_tree.item(item_id, tags=(tag,))

        updated_values = list(self.result_tree.item(item_id, "values"))
        for index, file_data in enumerate(self.all_files):
            if str(file_data[2]) == path:
                self.all_files[index] = updated_values
                break

    def _status_tag(self, status: str) -> str:
        if status == "✓":
            return "nude"
        if status == "✗":
            return "safe"
        if status == "BAD":
            return "bad"
        return ""

    def _matches_filter(self, status: str, filter_type: str | None = None) -> bool:
        current = filter_type or self.filter_var.get()
        if current == "Все":
            return True
        if current == "Только НЮ":
            return status == "✓"
        if current == "Только безопасные":
            return status == "✗"
        if current == "BAD":
            return status == "BAD"
        if current == "Неопределённые":
            return status not in {"", "✓", "✗", "BAD"}
        return True

    def apply_filter(self, _event=None) -> None:
        self.result_tree.delete(*self.result_tree.get_children())
        for file_data in self.all_files:
            status = str(file_data[6]).strip()
            if self._matches_filter(status):
                self._insert_row(file_data)

    def sort_treeview_column(self, column: str, reverse: bool) -> None:
        rows = [(self.result_tree.set(item, column), item) for item in self.result_tree.get_children("")]

        def sort_key(entry):
            value = entry[0]
            if column in {"#", "Оценка"}:
                try:
                    return (0, float(str(value).replace(",", ".")))
                except ValueError:
                    return (1, str(value).casefold())
            return (0, str(value).casefold())

        rows.sort(key=sort_key, reverse=reverse)
        for position, (_, item) in enumerate(rows):
            self.result_tree.move(item, "", position)
        self.result_tree.heading(
            column,
            command=lambda: self.sort_treeview_column(column, not reverse),
        )

    def _target_subfolder(self) -> str | None:
        mapping = {
            "Только НЮ": "NU",
            "Неопределённые": "UNKNOWN",
            "BAD": "BAD",
        }
        return mapping.get(self.filter_var.get())

    def move_selected_file_by_filter(self, _event=None) -> None:
        target_subfolder = self._target_subfolder()
        if target_subfolder is None:
            messagebox.showinfo("Инфо", "Для перемещения выберите фильтр НЮ, Неопределённые или BAD")
            return

        selected = self.result_tree.selection()
        if not selected:
            return
        self._move_items(selected, target_subfolder)

    def move_images_by_filter(self) -> None:
        target_subfolder = self._target_subfolder()
        if target_subfolder is None:
            messagebox.showinfo("Инфо", "Для перемещения выберите фильтр НЮ, Неопределённые или BAD")
            return

        visible = self.result_tree.get_children()
        if not visible:
            return
        self._move_items(visible, target_subfolder)

    def _move_items(self, item_ids, target_subfolder: str) -> None:
        base = Path(self.path_entry.get()).resolve()
        target_root = base / target_subfolder
        moved = 0

        for item_id in item_ids:
            if not self.result_tree.exists(item_id):
                continue
            values = list(self.result_tree.item(item_id, "values"))
            if len(values) < 7:
                continue

            status = str(values[6]).strip()
            if not self._matches_filter(status):
                continue

            source = Path(str(values[2])).resolve()
            try:
                relative = source.relative_to(base)
            except ValueError:
                relative = Path(source.name)

            destination = target_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination = self._unique_destination(destination)

            try:
                shutil.move(str(source), str(destination))
                self._replace_path(str(source), str(destination))
                self.result_tree.set(item_id, "Путь", str(destination))
                log_message(f"[MOVE] {source} -> {destination}\n", self.log_console)
                moved += 1
            except OSError as exc:
                log_message(f"[ERROR MOVE] {source}: {exc}\n", self.log_console)

        self.status_var.set(f"Перемещено {moved} файлов в {target_root}")
        if moved:
            messagebox.showinfo("Готово", f"Перемещено {moved} файлов")

    def _unique_destination(self, destination: Path) -> Path:
        if not destination.exists():
            return destination
        for index in range(1, 10_000):
            candidate = destination.with_name(f"{destination.stem}__{index}{destination.suffix}")
            if not candidate.exists():
                return candidate
        raise RuntimeError(f"Не удалось подобрать свободное имя для {destination}")

    def _replace_path(self, old_path: str, new_path: str) -> None:
        for file_data in self.all_files:
            if str(file_data[2]) == old_path:
                file_data[2] = new_path
                file_data[1] = Path(new_path).name
                return

    def delete_selected_file(self, _event=None) -> None:
        selected = self.result_tree.selection()
        if not selected:
            return

        for item_id in selected:
            values = self.result_tree.item(item_id, "values")
            if len(values) < 3:
                continue
            img_path = str(values[2])
            try:
                Path(img_path).unlink()
                self.all_files = [row for row in self.all_files if str(row[2]) != img_path]
                self.result_tree.delete(item_id)
                log_message(f"[DELETE] {img_path}\n", self.log_console)
            except OSError as exc:
                log_message(f"[ERROR DELETE] {img_path}: {exc}\n", self.log_console)

    def open_image(self, _event=None) -> None:
        selected = self.result_tree.selection()
        if not selected:
            return
        img_path = str(self.result_tree.item(selected[0], "values")[2])
        try:
            if sys.platform.startswith("win"):
                os.startfile(img_path)
            elif sys.platform == "darwin":
                subprocess.Popen(("open", img_path))
            else:
                subprocess.Popen(("xdg-open", img_path))
        except OSError as exc:
            messagebox.showerror("Ошибка", f"Не удалось открыть изображение: {exc}")

    def show_preview(self, _event=None) -> None:
        selected = self.result_tree.selection()
        if not selected:
            return

        img_path = str(self.result_tree.item(selected[0], "values")[2])
        self._last_preview_path = img_path
        try:
            with Image.open(img_path) as image:
                image = image.convert("RGB")
                preview_width = max(1, self.preview_frame.winfo_width() - 20)
                preview_height = max(1, self.preview_frame.winfo_height() - 20)
                image.thumbnail((preview_width, preview_height), Image.Resampling.LANCZOS)
                tk_image = ImageTk.PhotoImage(image.copy())
            self.preview_label.config(image=tk_image, text="")
            self.preview_label.image = tk_image
        except (OSError, ValueError) as exc:
            self.preview_label.config(image="", text="Не удалось загрузить изображение")
            self.preview_label.image = None
            log_message(f"[PREVIEW] {img_path}: {exc}\n", self.log_console)

    def on_close(self) -> None:
        self.running = False
        self.stop_analysis = True
        self.root.destroy()
