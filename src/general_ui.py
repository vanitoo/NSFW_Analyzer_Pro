from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from PIL import Image, ImageTk

from .general_classifier import GeneralImageClassifier
from .scanner import scan_folder_async
from .utils import log_message


class GeneralClassifierWindow:
    """Experimental general-purpose image organizer in an isolated Toplevel."""

    COLUMNS = (
        "#",
        "Имя файла",
        "Путь",
        "Размер",
        "Дата изменения",
        "Тип",
        "Категория",
        "Подкатегория",
        "Score",
        "Топ-5",
    )

    def __init__(self, parent: tk.Misc, initial_folder: str = "") -> None:
        self.window = tk.Toplevel(parent)
        self.window.title("Общий классификатор изображений — эксперимент")
        self.window.geometry("1500x850")
        self.window.minsize(1100, 650)
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)

        self.running = True
        self.stop_analysis = False
        self.image_queue: queue.Queue = queue.Queue()
        self.scan_thread: threading.Thread | None = None
        self.classify_thread: threading.Thread | None = None
        self.classifier: GeneralImageClassifier | None = None

        self.all_files: list[list] = []
        self.path_to_item: dict[str, str] = {}

        self._create_widgets()
        if initial_folder:
            self.path_entry.insert(0, initial_folder)

        self.window.after(100, self.process_queue)
        self.status_var.set("Выберите папку и нажмите «Сканировать»")

    def _create_widgets(self) -> None:
        controls = tk.Frame(self.window)
        controls.pack(fill=tk.X, padx=6, pady=6)
        controls.columnconfigure(1, weight=1)

        tk.Label(controls, text="Папка:").grid(row=0, column=0, padx=4)
        self.path_entry = tk.Entry(controls)
        self.path_entry.grid(row=0, column=1, padx=4, sticky="ew")

        self.browse_button = tk.Button(controls, text="Обзор", command=self.browse_folder)
        self.browse_button.grid(row=0, column=2, padx=4)

        self.scan_button = tk.Button(controls, text="Сканировать", command=self.start_scan)
        self.scan_button.grid(row=0, column=3, padx=4)

        self.classify_button = tk.Button(
            controls,
            text="Классифицировать",
            command=self.toggle_classification,
            state=tk.DISABLED,
        )
        self.classify_button.grid(row=0, column=4, padx=4)

        tk.Label(
            controls,
            text="Модель: MobileCLIP2-S0 / OpenCLIP",
        ).grid(row=0, column=5, padx=10)

        tk.Label(controls, text="Тип:").grid(row=1, column=0, padx=4, pady=(6, 0))
        self.kind_filter = tk.StringVar(value="Все типы")
        self.kind_combo = ttk.Combobox(
            controls,
            textvariable=self.kind_filter,
            values=("Все типы",),
            state="readonly",
            width=18,
        )
        self.kind_combo.grid(row=1, column=1, padx=4, pady=(6, 0), sticky="w")
        self.kind_combo.bind("<<ComboboxSelected>>", self.apply_filter)

        tk.Label(controls, text="Категория:").grid(row=1, column=2, padx=4, pady=(6, 0))
        self.category_filter = tk.StringVar(value="Все категории")
        self.category_combo = ttk.Combobox(
            controls,
            textvariable=self.category_filter,
            values=("Все категории",),
            state="readonly",
            width=20,
        )
        self.category_combo.grid(row=1, column=3, padx=4, pady=(6, 0), sticky="w")
        self.category_combo.bind("<<ComboboxSelected>>", self.apply_filter)

        tk.Label(controls, text="Подкатегория:").grid(row=1, column=4, padx=4, pady=(6, 0))
        self.subcategory_filter = tk.StringVar(value="Все подкатегории")
        self.subcategory_combo = ttk.Combobox(
            controls,
            textvariable=self.subcategory_filter,
            values=("Все подкатегории",),
            state="readonly",
            width=26,
        )
        self.subcategory_combo.grid(row=1, column=5, padx=4, pady=(6, 0), sticky="w")
        self.subcategory_combo.bind("<<ComboboxSelected>>", self.apply_filter)

        main = tk.PanedWindow(self.window, orient=tk.HORIZONTAL)
        main.pack(fill=tk.BOTH, expand=True)

        left = tk.PanedWindow(main, orient=tk.VERTICAL)
        main.add(left, width=1160)

        tree_frame = tk.Frame(left)
        left.add(tree_frame, height=570)

        scroll_y = ttk.Scrollbar(tree_frame)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        scroll_x = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL)
        scroll_x.pack(side=tk.BOTTOM, fill=tk.X)

        self.tree = ttk.Treeview(
            tree_frame,
            columns=self.COLUMNS,
            show="headings",
            yscrollcommand=scroll_y.set,
            xscrollcommand=scroll_x.set,
        )
        self.tree.pack(fill=tk.BOTH, expand=True)
        scroll_y.config(command=self.tree.yview)
        scroll_x.config(command=self.tree.xview)

        widths = {
            "#": 50,
            "Имя файла": 200,
            "Путь": 320,
            "Размер": 85,
            "Дата изменения": 130,
            "Тип": 100,
            "Категория": 120,
            "Подкатегория": 175,
            "Score": 80,
            "Топ-5": 390,
        }
        for column in self.COLUMNS:
            self.tree.heading(column, text=column)
            self.tree.column(
                column,
                width=widths[column],
                anchor="center" if column in {"#", "Тип", "Категория", "Подкатегория", "Score"} else "w",
            )

        log_frame = tk.LabelFrame(left, text="Лог")
        left.add(log_frame, height=220)
        self.log_console = scrolledtext.ScrolledText(log_frame, height=8)
        self.log_console.pack(fill=tk.BOTH, expand=True)

        preview_frame = tk.LabelFrame(main, text="Превью")
        main.add(preview_frame, width=330)
        self.preview_label = tk.Label(preview_frame, text="Выберите изображение")
        self.preview_label.pack(fill=tk.BOTH, expand=True)

        status_frame = tk.Frame(self.window, bd=1, relief=tk.SUNKEN)
        status_frame.pack(fill=tk.X, side=tk.BOTTOM)
        self.status_var = tk.StringVar()
        tk.Label(status_frame, textvariable=self.status_var, anchor="w").pack(
            side=tk.LEFT,
            fill=tk.X,
            expand=True,
            padx=5,
        )
        self.progress = ttk.Progressbar(status_frame, maximum=1, length=360)
        self.progress.pack(side=tk.RIGHT, padx=5)

        self.tree.bind("<<TreeviewSelect>>", self.show_preview)
        self.tree.bind("<Double-1>", self.open_image)
        self.tree.bind("<Return>", self.open_image)

    def browse_folder(self) -> None:
        folder = filedialog.askdirectory(parent=self.window)
        if not folder:
            return
        self.path_entry.delete(0, tk.END)
        self.path_entry.insert(0, folder)

    def start_scan(self) -> None:
        folder = self.path_entry.get().strip()
        if not folder:
            messagebox.showerror("Ошибка", "Выберите папку", parent=self.window)
            return

        self.stop_analysis = False
        self.all_files.clear()
        self.path_to_item.clear()
        self.tree.delete(*self.tree.get_children())
        self._reset_filters()
        self.classify_button.config(state=tk.DISABLED)
        self.scan_button.config(state=tk.DISABLED)
        self.browse_button.config(state=tk.DISABLED)
        self.status_var.set("Сканирование...")

        self.scan_thread = threading.Thread(
            target=scan_folder_async,
            args=(self, folder),
            daemon=True,
            name="general-folder-scan",
        )
        self.scan_thread.start()

    def toggle_classification(self) -> None:
        if self.classify_thread and self.classify_thread.is_alive():
            self.stop_analysis = True
            self.classify_button.config(text="Останавливаю...", state=tk.DISABLED)
            return
        self.start_classification()

    def start_classification(self) -> None:
        if not self.all_files:
            return

        self.stop_analysis = False
        self.scan_button.config(state=tk.DISABLED)
        self.browse_button.config(state=tk.DISABLED)
        self.classify_button.config(text="Остановить", state=tk.NORMAL)
        self.progress["maximum"] = len(self.all_files)
        self.progress["value"] = 0
        self.status_var.set("Подготовка MobileCLIP2-S0...")

        self.classify_thread = threading.Thread(
            target=self._classification_worker,
            daemon=True,
            name="general-classifier",
        )
        self.classify_thread.start()

    def _classification_worker(self) -> None:
        try:
            if self.classifier is None:
                self.classifier = GeneralImageClassifier(
                    lambda message: self.image_queue.put(("log", message))
                )
            self.classifier.load()
        except Exception as exc:
            self.image_queue.put(("classification_error", str(exc)))
            return

        total = len(self.all_files)
        processed = 0
        for row in list(self.all_files):
            if self.stop_analysis or not self.running:
                break

            path = str(row[2])
            try:
                result = self.classifier.classify(path)
                self.image_queue.put(("general_result", path, result))
            except Exception as exc:
                self.image_queue.put(("log", f"[General][SKIP] {path}: {exc}\n"))
                self.image_queue.put(
                    (
                        "general_result",
                        path,
                        {
                            "kind": "Ошибка",
                            "category": "Ошибка",
                            "subcategory": "",
                            "score": 0.0,
                            "tags": str(exc),
                        },
                    )
                )

            processed += 1
            self.image_queue.put(("progress", processed))
            self.image_queue.put(("status", f"Классификация... ({processed}/{total})"))

        self.image_queue.put(("classification_complete", processed, total, self.stop_analysis))

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

                elif event == "scan_start":
                    total = max(1, int(task[1]))
                    self.progress["maximum"] = total
                    self.progress["value"] = 0

                elif event == "scan_batch":
                    for scan_row in task[1]:
                        row = list(scan_row[:5]) + ["", "", "", "", ""]
                        self.all_files.append(row)
                        self._insert_row(row)

                elif event == "progress":
                    self.progress["value"] = int(task[1])

                elif event == "scan_complete":
                    count = int(task[1])
                    self.progress["value"] = count
                    self.status_var.set(f"Найдено {count} изображений")
                    self.scan_button.config(state=tk.NORMAL)
                    self.browse_button.config(state=tk.NORMAL)
                    self.classify_button.config(state=tk.NORMAL if count else tk.DISABLED)

                elif event == "scan_cancelled":
                    self.status_var.set(f"Сканирование остановлено ({task[1]})")
                    self.scan_button.config(state=tk.NORMAL)
                    self.browse_button.config(state=tk.NORMAL)

                elif event == "general_result":
                    self._apply_result(str(task[1]), task[2])

                elif event == "classification_complete":
                    processed, total, stopped = int(task[1]), int(task[2]), bool(task[3])
                    self._refresh_filter_values()
                    self.apply_filter()
                    self.classify_thread = None
                    self.scan_button.config(state=tk.NORMAL)
                    self.browse_button.config(state=tk.NORMAL)
                    self.classify_button.config(text="Классифицировать", state=tk.NORMAL)
                    if stopped:
                        self.status_var.set(f"Классификация остановлена ({processed}/{total})")
                    else:
                        self.status_var.set(f"Классификация завершена ({processed}/{total})")

                elif event == "classification_error":
                    self.classify_thread = None
                    self.scan_button.config(state=tk.NORMAL)
                    self.browse_button.config(state=tk.NORMAL)
                    self.classify_button.config(text="Классифицировать", state=tk.NORMAL)
                    self.status_var.set("Ошибка общего классификатора")
                    messagebox.showerror("MobileCLIP2", task[1], parent=self.window)

        except queue.Empty:
            pass

        if self.running and self.window.winfo_exists():
            self.window.after(100, self.process_queue)

    def _insert_row(self, row: list) -> None:
        item = self.tree.insert("", "end", values=row)
        self.path_to_item[str(row[2])] = item

    def _apply_result(self, path: str, result: dict) -> None:
        for row in self.all_files:
            if str(row[2]) == path:
                row[5] = str(result.get("kind", ""))
                row[6] = str(result.get("category", ""))
                row[7] = str(result.get("subcategory", ""))
                row[8] = f"{float(result.get('score', 0.0)):.4f}"
                row[9] = str(result.get("tags", ""))
                break

        item = self.path_to_item.get(path)
        if item and self.tree.exists(item):
            self.tree.item(item, values=row)

    def _reset_filters(self) -> None:
        self.kind_filter.set("Все типы")
        self.category_filter.set("Все категории")
        self.subcategory_filter.set("Все подкатегории")
        self.kind_combo["values"] = ("Все типы",)
        self.category_combo["values"] = ("Все категории",)
        self.subcategory_combo["values"] = ("Все подкатегории",)

    def _refresh_filter_values(self) -> None:
        kinds = sorted({str(row[5]) for row in self.all_files if str(row[5])})
        categories = sorted({str(row[6]) for row in self.all_files if str(row[6])})
        subcategories = sorted({str(row[7]) for row in self.all_files if str(row[7])})
        self.kind_combo["values"] = ("Все типы", *kinds)
        self.category_combo["values"] = ("Все категории", *categories)
        self.subcategory_combo["values"] = ("Все подкатегории", *subcategories)

    def apply_filter(self, _event=None) -> None:
        kind = self.kind_filter.get()
        category = self.category_filter.get()
        subcategory = self.subcategory_filter.get()

        self.tree.delete(*self.tree.get_children())
        self.path_to_item.clear()

        for row in self.all_files:
            if kind != "Все типы" and str(row[5]) != kind:
                continue
            if category != "Все категории" and str(row[6]) != category:
                continue
            if subcategory != "Все подкатегории" and str(row[7]) != subcategory:
                continue
            self._insert_row(row)

    def show_preview(self, _event=None) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        values = self.tree.item(selected[0], "values")
        if len(values) < 3:
            return

        path = str(values[2])
        try:
            with Image.open(path) as image:
                image = image.convert("RGB")
                image.thumbnail((310, 700), Image.Resampling.LANCZOS)
                tk_image = ImageTk.PhotoImage(image.copy())
            self.preview_label.config(image=tk_image, text="")
            self.preview_label.image = tk_image
        except (OSError, ValueError) as exc:
            self.preview_label.config(image="", text=f"Ошибка превью: {exc}")
            self.preview_label.image = None

    def open_image(self, _event=None) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        values = self.tree.item(selected[0], "values")
        if len(values) < 3:
            return
        path = str(values[2])
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(("open", path))
            else:
                subprocess.Popen(("xdg-open", path))
        except OSError as exc:
            messagebox.showerror("Ошибка", str(exc), parent=self.window)

    def on_close(self) -> None:
        self.running = False
        self.stop_analysis = True
        self.window.destroy()
