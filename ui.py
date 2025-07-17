import datetime
import functools
import os
import queue
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext

from PIL import Image, ImageTk

from analyzer import initialize_model, analyze_images
from scanner import scan_folder_async, update_file_list
from utils import log_message


class NSFWAnalyzerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("NSFW Analyzer Pro")
        self.root.geometry("1400x800")

        self.scan_folder_async = functools.partial(scan_folder_async, self)
        self.initialize_model = functools.partial(initialize_model, self)
        self.analyze_images = functools.partial(analyze_images, self)
        self.update_file_list = functools.partial(update_file_list, self)

        # Базовые переменные (не блокирующие загрузку)
        self.stop_analysis = False
        self.analysis_thread = None
        self.image_queue = queue.Queue()
        self.model_loaded = False
        self.model = None
        self.libs_loaded = False  # Добавлено
        self.running = True
        self.predict_fn = None  # Добавляем инициализацию атрибута

        self.all_files = []  # Список всех файлов для фильтрации

        # Создание интерфейса
        self.create_widgets()

        # Обработка сообщений из очереди
        self.root.after(100, self.process_queue)

        # # Инициализация прогресс-бара
        # # self.progress = ttk.Progressbar(self.status_bar, mode='indeterminate', length=200)
        # self.progress = ttk.Progressbar(self.status_bar, mode='determinate', length=600, maximum=100)
        # self.progress.pack(side=tk.RIGHT, padx=5)

        self.start_background_loading()
        threading.Thread(target=self.initialize_backend, daemon=True).start()

    def start_background_loading(self):
        """Запускает фоновую загрузку тяжелых зависимостей"""

        def load_in_background():
            try:
                # Загружаем только PIL (остальные модели будем грузить по требованию)
                from PIL import Image, ImageTk
                self.Image = Image
                self.ImageTk = ImageTk
                self.libs_loaded = True
                log_message("Базовые библиотеки загружены\n")
            except Exception as e:
                log_message(f"Ошибка загрузки библиотек: {e}\n")

        threading.Thread(target=load_in_background, daemon=True).start()
        self.root.after(100, self.check_loading_status)

    def check_loading_status(self):
        """Проверяет прогресс загрузки"""
        if self.libs_loaded:
            self.finish_ui_setup()
        else:
            self.root.after(100, self.check_loading_status)

    def finish_ui_setup(self):
        """Дозагружает компоненты, требующие библиотек"""
        # Здесь инициализация превью и других зависимых элементов
        # self.preview_label = tk.Label(self.preview_frame)
        # self.preview_label.pack(fill=tk.BOTH, expand=True)

        # Активируем кнопки
        self.analyze_button.config(state=tk.NORMAL)

    def initialize_backend(self):
        """Инициализирует тяжелые компоненты в фоне"""
        # Проверка GPU/CPU
        import tensorflow as tf
        devices = tf.config.list_physical_devices()
        self.image_queue.put(("log", f"Доступные устройства: {devices}\n"))

        # Ленивая загрузка модели при первом анализе
        # self.image_queue.put(("log", "Модель будет загружена при первом анализе\n"))

        # Обновляем статус
        self.image_queue.put(("status", "Готов к работе"))

    def create_widgets(self):
        # Панель управления
        self.control_frame = tk.Frame(self.root)
        self.control_frame.pack(fill=tk.X, padx=5, pady=5)

        # Основной контейнер
        self.main_paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.main_paned.pack(fill=tk.BOTH, expand=True)

        # Левая панель (таблица + лог)
        self.left_paned = tk.PanedWindow(self.main_paned, orient=tk.VERTICAL)
        self.main_paned.add(self.left_paned, width=950)

        # Правая панель (превью)
        self.preview_frame = tk.LabelFrame(self.main_paned, text="Превью")
        self.main_paned.add(self.preview_frame, width=300)

        # Превью изображения
        # self.preview_frame = tk.LabelFrame(self.main_paned, text="Превью")
        # self.preview_label = tk.Label(self.preview_frame)
        # self.preview_label.pack(fill=tk.BOTH, expand=True)

        # Обработчик изменения размера окна (добавьте эти строки)
        # self.preview_frame.bind("<Configure>", self.resize_preview)
        # self.root.bind("<Configure>", lambda e: self.resize_preview())

        # # Панель управления
        # self.control_frame = tk.Frame(self.root)
        # self.control_frame.pack(fill=tk.X, padx=5, pady=5)

        # Элементы управления
        tk.Label(self.control_frame, text="Папка:").grid(row=0, column=0, padx=5)
        self.path_entry = tk.Entry(self.control_frame, width=50)
        self.path_entry.grid(row=0, column=1, padx=5, sticky='ew')

        self.browse_button = tk.Button(self.control_frame, text="Обзор", command=self.browse_folder)
        self.browse_button.grid(row=0, column=2, padx=5)

        tk.Label(self.control_frame, text="Порог:").grid(row=0, column=3, padx=5)
        self.threshold_slider = tk.Scale(self.control_frame, from_=0.1, to=1.0, resolution=0.01,
                                         orient=tk.HORIZONTAL, length=200)
        self.threshold_slider.set(0.7)
        self.threshold_slider.grid(row=0, column=4, padx=5)

        tk.Label(self.control_frame, text="Фильтр:").grid(row=0, column=5, padx=5)
        self.filter_var = tk.StringVar(value="all")
        self.filter_combobox = ttk.Combobox(
            self.control_frame,
            textvariable=self.filter_var,
            values=["Все", "Только НЮ", "Только безопасные", "Неопределённые", "BAD"],  # 👈 добавили BAD
            state="readonly",
            width=15
        )

        # self.filter_combobox = ttk.Combobox(self.control_frame, textvariable=self.filter_var,
        #                                     values=["Все", "Только НЮ", "Только безопасные", "Неопределённые"],
        #                                     state="readonly", width=15)
        self.filter_combobox.grid(row=0, column=6, padx=5)

        self.analyze_button = tk.Button(self.control_frame, text="Анализировать", command=self.toggle_analysis)
        self.analyze_button.grid(row=0, column=7, padx=5)

        self.move_button = tk.Button(
            self.control_frame,
            text="Переместить",
            command=self.move_images_by_filter,
            state=tk.DISABLED
        )
        self.move_button.grid(row=0, column=8, padx=5)

        tk.Label(self.control_frame, text="Модель:").grid(row=0, column=9, padx=5)
        self.model_type = tk.StringVar(value="yahoo")
        self.model_combobox = ttk.Combobox(
            self.control_frame,
            textvariable=self.model_type,
            values=["Yahoo NSFW", "MobileNetV2", "GantMan NSFW", "NSFW Hub Detector", "TF Hub Detector"],
            state="readonly",
            width=15
        )
        self.model_combobox.grid(row=0, column=10, padx=5)

        # Таблица результатов
        self.tree_frame = tk.Frame(self.left_paned)
        self.left_paned.add(self.tree_frame, height=500)

        self.tree_scroll_y = ttk.Scrollbar(self.tree_frame)
        self.tree_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree_scroll_x = ttk.Scrollbar(self.tree_frame, orient=tk.HORIZONTAL)
        self.tree_scroll_x.pack(side=tk.BOTTOM, fill=tk.X)

        self.result_tree = ttk.Treeview(self.tree_frame,
                                        columns=("#", "Имя файла", "Путь", "Размер", "Дата изменения", "Порог", "Статус"),
                                        show="headings",
                                        yscrollcommand=self.tree_scroll_y.set,
                                        xscrollcommand=self.tree_scroll_x.set)

        self.result_tree.pack(fill=tk.BOTH, expand=True)

        self.tree_scroll_y.config(command=self.result_tree.yview)
        self.tree_scroll_x.config(command=self.result_tree.xview)

        # Настройка столбцов
        columns = {
            "#": {"width": 50, "anchor": "center"},
            "Имя файла": {"width": 200},
            "Путь": {"width": 300},
            "Размер": {"width": 80, "anchor": "e"},
            "Дата изменения": {"width": 120},
            "Порог": {"width": 80, "anchor": "center"},
            "Статус": {"width": 60, "anchor": "center"}
        }

        # for col, params in columns.items():
        #     self.result_tree.heading(col, text=col)
        #     self.result_tree.column(col, **params)

        for col, params in columns.items():
            self.result_tree.heading(col, text=col,
                                     command=lambda c=col: self.sort_treeview_column(c, False))
            self.result_tree.column(col, **params)

        # Теги для подсветки
        self.result_tree.tag_configure('nude', background='#ffcccc')
        self.result_tree.tag_configure('safe', background='#ccffcc')

        # Консоль логов
        self.log_frame = tk.LabelFrame(self.left_paned, text="Лог")
        self.left_paned.add(self.log_frame, height=200)

        self.log_console = scrolledtext.ScrolledText(self.log_frame)
        self.log_console.pack(fill=tk.BOTH, expand=True)

        # # Превью изображения
        self.preview_label = tk.Label(self.preview_frame)
        self.preview_label.pack(fill=tk.BOTH, expand=True)

        # # Статус бар
        # status_frame = tk.Frame(self.root)
        # status_frame.pack(side="bottom", fill="x")
        # #
        # self.status_bar = tk.Label(status_frame, text="", anchor="w", width=60)  # фикс ширина
        # self.status_bar.pack(side="left", padx=5)
        # #
        # # self.progress = ttk.Progressbar(status_frame, orient="horizontal", length=300, mode="determinate")
        # # self.progress.pack(side="right", padx=5)
        #
        # self.status_var = tk.StringVar()
        # self.status_bar = tk.Label(self.root, textvariable=self.status_var, bd=1, relief=tk.SUNKEN, anchor=tk.W)
        # self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)
        # #
        # # # Инициализация прогресс-бара
        # # # self.progress = ttk.Progressbar(self.status_bar, mode='indeterminate', length=200)
        # self.progress = ttk.Progressbar(self.status_bar, mode='determinate', length=600, maximum=100)
        # self.progress.pack(side=tk.RIGHT, padx=5)

        # Создаём контейнер для статуса и прогрессбара
        status_frame = tk.Frame(self.root, bd=1, relief=tk.SUNKEN)
        status_frame.pack(side="bottom", fill="x")

        # Статус-текст
        self.status_var = tk.StringVar()
        self.status_bar = tk.Label(status_frame, textvariable=self.status_var, anchor="w", width=60)
        self.status_bar.pack(side="left", padx=5)

        # Прогресс-бар
        self.progress = ttk.Progressbar(status_frame, mode="determinate", length=300, maximum=100)
        self.progress.pack(side="right", padx=5)

        # Привязка событий
        self.result_tree.bind("<Double-1>", self.open_image)
        self.result_tree.bind("<<TreeviewSelect>>", self.show_preview)
        self.filter_var.trace_add('write', self.apply_filter)

        # Enter – открыть изображение
        self.result_tree.bind("<Return>", self.open_image)
        # F6 – перемещение
        self.root.bind("<F6>", self.move_selected_file_by_filter)
        # Del – удалить файл
        self.root.bind("<Delete>", self.delete_selected_file)

        self.result_tree.tag_configure('mobilenet', background='#e0f7ff')
        self.result_tree.tag_configure('bad', background='#ffe680')
        self.result_tree.tag_configure('nude', background='#ffcccc')
        self.result_tree.tag_configure('safe', background='#ccffcc')

    def mark_bad_file(self, img_path):
        # Находим item в Treeview
        for item in self.result_tree.get_children():
            values = list(self.result_tree.item(item)['values'])
            if values[2] == img_path:
                # Обновляем в Treeview
                self.result_tree.set(item, "НЮ", "BAD")
                self.result_tree.item(item, tags=("bad",))
                # Обновляем в all_files
                for i, f in enumerate(self.all_files):
                    if f[2] == img_path:
                        updated = list(f)
                        updated[6] = "BAD"
                        self.all_files[i] = tuple(updated)
                        break
                break

    def move_selected_file_by_filter(self, event=None):
        folder_path = self.path_entry.get()
        if not folder_path:
            return

        filter_type = self.filter_var.get()
        if filter_type == "Только НЮ":
            target_subfolder = "NU"
        elif filter_type == "Неопределённые":
            target_subfolder = "BAD"
        else:
            messagebox.showinfo("Инфо", "Перемещение доступно только для фильтров 'Только НЮ' и 'Неопределённые'")
            return

        selected = self.result_tree.selection()
        if not selected:
            return  # ничего не выбрано

        target_folder = os.path.join(folder_path, target_subfolder)
        os.makedirs(target_folder, exist_ok=True)

        moved_count = 0
        for item in selected:
            values = self.result_tree.item(item)['values']
            img_path = values[2]
            nude_status = str(values[6]).strip()

            # проверяем статус по фильтру
            if filter_type == "Только НЮ" and nude_status != "✓":
                continue
            if filter_type == "Неопределённые" and nude_status in ("✓", "✗"):
                continue

            try:
                filename = os.path.basename(img_path)
                dst_path = os.path.join(target_folder, filename)
                os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                os.rename(img_path, dst_path)
                log_message(f"[MOVE ONE] {img_path} -> {dst_path}\n", self.log_console)
                self.result_tree.set(item, "Путь", dst_path)
                moved_count += 1
            except Exception as e:
                log_message(f"[ERROR MOVE ONE] {img_path}: {e}\n", self.log_console)

        if moved_count > 0:
            self.status_var.set(f"Перемещён {moved_count} файл(ов) в {target_folder}")

    def delete_selected_file(self, event=None):
        selected = self.result_tree.selection()
        if not selected:
            return
        for item in selected:
            img_path = self.result_tree.item(item)['values'][2]
            try:
                os.remove(img_path)
                log_message(f"[DELETE] {img_path}\n", self.log_console)
                self.result_tree.delete(item)
            except Exception as e:
                log_message(f"[ERROR DELETE] {img_path}: {e}\n", self.log_console)

    def move_images_by_filter(self, *_):
        folder_path = self.path_entry.get()
        if not folder_path:
            return

        filter_type = self.filter_var.get()
        if filter_type == "Только НЮ":
            target_subfolder = "NU"
        elif filter_type == "Неопределённые":
            target_subfolder = "BAD"
        else:
            messagebox.showinfo("Инфо", "Перемещение доступно только для фильтров 'Только НЮ' и 'Неопределённые'")
            return

        target_folder = os.path.join(folder_path, target_subfolder)
        os.makedirs(target_folder, exist_ok=True)

        moved_count = 0
        for item in self.result_tree.get_children():
            values = self.result_tree.item(item)['values']
            img_path = values[2]
            nude_status = str(values[6]).strip()
            # Логика отбора по фильтру
            if filter_type == "Только НЮ" and nude_status != "✓":
                continue
            if filter_type == "Неопределённые" and nude_status in ("✓", "✗"):
                continue

            try:
                filename = os.path.basename(img_path)
                dst_path = os.path.join(target_folder, filename)
                os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                os.rename(img_path, dst_path)
                log_message(f"[MOVE] {img_path} -> {dst_path}\n", self.log_console)
                self.result_tree.set(item, "Путь", dst_path)
                moved_count += 1
            except Exception as e:
                log_message(f"[ERROR MOVE] {img_path}: {e}\n", self.log_console)

        self.status_var.set(f"Перемещено {moved_count} файлов в {target_folder}")
        messagebox.showinfo("Готово", f"Перемещено {moved_count} файлов")

    def move_nude_images(self):
        folder_path = self.path_entry.get()
        if not folder_path:
            return

        # Создаем папку NU в корневой директории
        target_folder = os.path.join(folder_path, "NU")
        os.makedirs(target_folder, exist_ok=True)

        moved_count = 0

        for item in self.result_tree.get_children():
            if self.result_tree.set(item, "НЮ") == "✓":
                src_path = self.result_tree.item(item)['values'][2]
                rel_path = os.path.relpath(src_path, folder_path)
                dst_path = os.path.join(target_folder, rel_path)

                # Создаем подпапки если нужно
                os.makedirs(os.path.dirname(dst_path), exist_ok=True)

                try:
                    shutil.move(src_path, dst_path)
                    moved_count += 1
                    # Обновляем путь в таблице
                    self.result_tree.set(item, "Путь", dst_path)
                except Exception as e:
                    log_message(f"Ошибка перемещения {src_path}: {e}\n")

        self.status_var.set(f"Перемещено {moved_count} файлов в {target_folder}")
        messagebox.showinfo("Готово", f"Перемещено {moved_count} файлов")

    def browse_folder(self):
        folder_path = filedialog.askdirectory()
        if not folder_path:
            return

        # Очищаем предыдущие результаты
        self.result_tree.delete(*self.result_tree.get_children())
        self.path_entry.delete(0, tk.END)
        self.path_entry.insert(0, folder_path)
        self.all_files.clear()

        # Запускаем сканирование в отдельном потоке
        threading.Thread(
            target=self.scan_folder_async,
            args=(folder_path,),
            daemon=True
        ).start()

    def load_images_from_folder(self, folder_path):
        self.result_tree.delete(*self.result_tree.get_children())
        if not folder_path:
            return

        supported_formats = ('.png', '.jpg', '.jpeg', '.bmp', '.gif')
        file_count = 0

        for root, _, files in os.walk(folder_path):
            for file in files:
                if file.lower().endswith(supported_formats):
                    file_count += 1
                    img_path = os.path.join(root, file)
                    stat = os.stat(img_path)
                    size = self.convert_size(stat.st_size)
                    mtime = datetime.datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M')

                    self.result_tree.insert("", "end", values=(
                        file_count,
                        os.path.basename(img_path),
                        img_path,
                        size,
                        mtime,
                        "",  # Для порога
                        ""  # Для статуса НЮ
                    ))

        self.status_var.set(f"Загружено {file_count} изображений")

    def toggle_analysis(self):
        if self.analyze_button['text'] == 'Анализировать':
            self.start_analysis()
        else:
            self.stop_analysis = True

    def start_analysis(self):
        if not self.path_entry.get():
            messagebox.showerror("Ошибка", "Выберите папку для анализа")
            return

        try:
            # Принудительная инициализация перед анализом
            if not hasattr(self, 'predict_fn'):
                log_message("⏳ Инициализация модели...\n", self.log_console)
                self.initialize_model()

            model_name = self.model_type.get()
            log_message(f"🔧 Модель {model_name} готова к работе\n", self.log_console)

        except Exception as e:
            log_message(f"❌ Критическая ошибка: {str(e)}\n", self.log_console)
            messagebox.showerror("Ошибка", f"Не удалось инициализировать модель:\n{str(e)}")
            return

        # Остальной код метода без изменений
        self.stop_analysis = False
        self.analyze_button.config(text="Остановить")
        # ...
        self.analysis_thread = threading.Thread(target=self.analyze_images, daemon=True)
        self.analysis_thread.start()

    def process_queue(self):
        if not getattr(self, "running", True):
            return

        try:
            while True:
                task = self.image_queue.get_nowait()

                if isinstance(task, tuple):
                    if task[0] == "update_item":
                        item_id = task[1]
                        values = task[2]

                        # Получаем путь до обновления
                        try:
                            tree_values = list(self.result_tree.item(item_id, "values"))
                            path = tree_values[2]
                        except Exception:
                            continue  # строка не найдена

                        # Обновляем Treeview
                        if self.result_tree.winfo_exists():
                            for col, val in values.items():
                                try:
                                    if col == "tag":
                                        self.result_tree.item(item_id, tags=(val,))
                                    else:
                                        self.result_tree.set(item_id, col, val)
                                except tk.TclError:
                                    continue  # удалена строка

                        # Получаем обновлённые значения после вставки
                        try:
                            updated_values = list(self.result_tree.item(item_id, "values"))
                        except Exception:
                            continue

                        # Обновляем all_files
                        for i, file_data in enumerate(self.all_files):
                            if file_data[2] == path:
                                self.all_files[i] = updated_values
                                break

                    elif task[0] == "log":
                        if self.log_console.winfo_exists():
                            try:
                                self.log_console.insert(tk.END, task[1])
                                self.log_console.see(tk.END)
                            except tk.TclError:
                                pass

                    elif task[0] == "status":
                        self.status_var.set(task[1])

                    elif task[0] == "scan_complete":
                        file_count = task[1]
                        self.status_var.set(f"Загружено {file_count} изображений. Готов к анализу")
                        self.progress.stop()
                        self.analyze_button.config(state=tk.NORMAL)

                    elif task[0] == "analysis_complete":
                        self.analyze_button.config(text="Анализировать", state=tk.NORMAL)
                        self.move_button.config(state=tk.NORMAL)

                    elif task[0] == "progress":
                        current = task[1]
                        self.progress["value"] = current
                        self.progress.update()

                    elif task[0] == "mark_bad":
                        bad_path = task[1]
                        self.mark_bad_file(bad_path)


        except queue.Empty:
            pass

        if self.running:
            self.root.after(100, self.process_queue)

    def apply_filter2(self, *args):
        if getattr(self, "analysis_running", False):
            messagebox.showwarning("Анализ", "Нельзя менять фильтр во время анализа.")
            return

        filter_type = self.filter_var.get()

        # Очищаем текущее отображение
        self.result_tree.delete(*self.result_tree.get_children())

        # Отображаем подходящие строки
        for file_data in self.all_files:
            nude_status = str(file_data[6]).strip()

            if filter_type == "Только НЮ" and nude_status != "✓":
                continue
            elif filter_type == "Только безопасные" and nude_status != "✗":
                continue
            elif filter_type == "Неопределённые" and nude_status in ("✓", "✗"):
                continue

            self.result_tree.insert("", "end", values=file_data)

        self.update_highlighting()

    def apply_filter(self, *args):
        if getattr(self, "analysis_running", False):
            messagebox.showwarning("Анализ", "Нельзя менять фильтр во время анализа.")
            return

        filter_type = self.filter_var.get()
        self.result_tree.delete(*self.result_tree.get_children())

        for file_data in self.all_files:
            nude_status = str(file_data[6]).strip()

            if filter_type == "Только НЮ" and nude_status != "✓":
                continue
            elif filter_type == "Только безопасные" and nude_status != "✗":
                continue
            elif filter_type == "Неопределённые" and nude_status in ("✓", "✗", "BAD"):
                continue
            elif filter_type == "BAD" and nude_status != "BAD":  # 👈 новый фильтр
                continue

            self.result_tree.insert("", "end", values=file_data)

        self.update_highlighting()

    def restore_all_items(self):
        """Восстанавливает все элементы в Treeview"""
        children = self.result_tree.get_children()
        for item in children:
            self.result_tree.reattach(item, '', 'end')

    def update_highlighting(self):
        """Обновляет подсветку всех видимых элементов"""
        for item in self.result_tree.get_children():
            nude_status = self.result_tree.set(item, "Статус")
            tags = ('nude',) if nude_status == "✓" else ('safe',) if nude_status == "✗" else ()
            self.result_tree.item(item, tags=tags)

    def open_image(self, event):
        selected_item = self.result_tree.selection()
        if selected_item:
            img_path = self.result_tree.item(selected_item[0])['values'][2]
            try:
                if sys.platform.startswith('win'):
                    os.startfile(img_path)
                elif sys.platform.startswith('darwin'):
                    subprocess.call(('open', img_path))
                else:
                    subprocess.call(('xdg-open', img_path))
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось открыть изображение: {e}")

    def show_preview(self, event=None):
        # получаем выбранный элемент
        selected = self.result_tree.selection()
        if not selected:
            return
        item = selected[0]
        img_path = self.result_tree.item(item)['values'][2]

        # сохраняем путь, чтобы не терять при ресайзе (если вдруг понадобится)
        self._last_preview_path = img_path

        try:
            img = Image.open(img_path)
            preview_width = self.preview_frame.winfo_width() - 20
            preview_height = self.preview_frame.winfo_height() - 20
            scale = min(preview_width / img.width, preview_height / img.height)
            new_size = (int(img.width * scale), int(img.height * scale))
            img = img.resize(new_size, Image.Resampling.LANCZOS)

            tk_img = ImageTk.PhotoImage(img)
            self.preview_label.config(image=tk_img, text="")  # сбрасываем текст
            self.preview_label.image = tk_img
        except Exception as e:
            self.preview_label.config(image=None, text="Не удалось загрузить изображение")
            print(f"Ошибка загрузки превью: {e}")

    # def resize_preview(self, event=None):
    #     # Перерисовываем только если есть текущая картинка
    #     if hasattr(self, "_last_preview_path") and self._last_preview_path:
    #         try:
    #             img = Image.open(self._last_preview_path)
    #             preview_width = self.preview_frame.winfo_width() - 20
    #             preview_height = self.preview_frame.winfo_height() - 20
    #             scale = min(preview_width / img.width, preview_height / img.height)
    #             new_size = (int(img.width * scale), int(img.height * scale))
    #             img = img.resize(new_size, Image.Resampling.LANCZOS)
    #             tk_img = ImageTk.PhotoImage(img)
    #             self.preview_label.config(image=tk_img)
    #             self.preview_label.image = tk_img
    #         except Exception as e:
    #             print(f"Ошибка ресайза превью: {e}")

    def on_close(self):
        self.running = False
        self.stop_analysis = True

        # Выгружаем модели из памяти
        if hasattr(self, 'n2'):
            del self.n2
        if hasattr(self, 'mobilenet_model'):
            del self.mobilenet_model
        if hasattr(self, 'tfhub_model'):
            del self.tfhub_model

        self.running = False  # останавливает process_queue
        self.stop_analysis = True  # остановить анализ

        # Очистка очереди ДО закрытия окна
        with self.image_queue.mutex:
            self.image_queue.queue.clear()

        # Ждём завершение анализа, если он ещё выполняется
        if self.analysis_thread and self.analysis_thread.is_alive():
            print("⏳ Ожидаем завершение анализа...")
            self.analysis_thread.join(timeout=3)

        # Теперь можно безопасно уничтожить окно
        self.root.destroy()
