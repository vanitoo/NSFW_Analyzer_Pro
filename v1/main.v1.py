#ver 1.0.0
import datetime
import os
import queue
import shutil
import subprocess
import sys
# import opennsfw2 as n2
import threading
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from tkinter import filedialog, ttk, messagebox, scrolledtext

from PIL import Image, ImageTk


class NSFWAnalyzerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("NSFW Analyzer Pro")
        self.root.geometry("1400x800")

        # Базовые переменные (не блокирующие загрузку)
        self.stop_analysis = False
        self.analysis_thread = None
        self.image_queue = queue.Queue()
        self.model_loaded = False
        self.model = None
        self.libs_loaded = False  # Добавлено

        self.all_files = []  # Список всех файлов для фильтрации

        self.model_type = tk.StringVar(value="yahoo")  # По умолчанию Yahoo
        self.create_widgets()

        # Обработка сообщений из очереди
        self.root.after(100, self.process_queue)

        # Инициализация прогресс-бара
        # self.progress = ttk.Progressbar(self.status_bar, mode='indeterminate', length=200)
        self.progress = ttk.Progressbar(self.status_bar, mode='determinate', length=600, maximum=100)
        self.progress.pack(side=tk.RIGHT, padx=5)

        self.start_background_loading()
        threading.Thread(target=self.initialize_backend, daemon=True).start()

    def scan_folder_async(self, folder_path):
        """Асинхронное сканирование папки"""
        self.status_var.set("Сканирование...")
        self.progress.start()
        self.analyze_button.config(state=tk.DISABLED)

        supported_formats = ('.png', '.jpg', '.jpeg', '.bmp', '.gif')
        file_count = 0
        batch = []

        for root, _, files in os.walk(folder_path):
            for file in files:
                if file.lower().endswith(supported_formats):
                    file_count += 1
                    img_path = os.path.join(root, file)

                    # Получаем метаданные
                    try:
                        stat = os.stat(img_path)
                        size = self.convert_size(stat.st_size)
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

    def start_background_loading(self):
        """Запускает фоновую загрузку тяжелых зависимостей"""

        def load_in_background():
            # 1. Загружаем TensorFlow и другие тяжелые библиотеки
            import tensorflow as tf
            import opennsfw2 as n2
            from PIL import Image, ImageTk

            # 2. Сохраняем ссылки
            self.tf = tf
            self.n2 = n2
            self.Image = Image
            self.ImageTk = ImageTk
            self.libs_loaded = True

            # 3. Инициализируем модель
            self.initialize_model()

            # 4. Обновляем UI
            self.log_message("Готов к работе\n")

        # Запускаем в отдельном потоке
        self.log_message("Загружается модель\n")
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

    def initialize_model(self):
        """Инициализирует модель при первом использовании"""
        if not self.model_loaded:
            self.image_queue.put(("status", "Загрузка модели..."))
            self.model = self.n2  # Для opennsfw2
            self.model_loaded = True

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
        self.preview_frame.bind("<Configure>", self.resize_preview)
        self.root.bind("<Configure>", lambda e: self.resize_preview())

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
        self.filter_combobox = ttk.Combobox(self.control_frame, textvariable=self.filter_var,
                                            values=["Все", "Только НЮ", "Только безопасные"],
                                            state="readonly", width=15)
        self.filter_combobox.grid(row=0, column=6, padx=5)

        self.analyze_button = tk.Button(self.control_frame, text="Анализировать", command=self.toggle_analysis)
        self.analyze_button.grid(row=0, column=7, padx=5)

        self.move_button = tk.Button(
            self.control_frame,
            text="Переместить НЮ",
            command=self.move_nude_images,
            state=tk.DISABLED
        )
        self.move_button.grid(row=0, column=8, padx=5)

        # tk.Label(self.control_frame, text="Модель:").grid(row=0, column=9, padx=5)
        # self.model_combobox = ttk.Combobox(
        #     self.control_frame,
        #     textvariable=self.model_type,
        #     values=["Yahoo NSFW", "MobileNetV2", "TensorFlow Hub"],
        #     state="readonly",
        #     width=15
        # )
        # self.model_combobox.grid(row=0, column=10, padx=5)


        # Таблица результатов
        self.tree_frame = tk.Frame(self.left_paned)
        self.left_paned.add(self.tree_frame, height=500)

        self.tree_scroll_y = ttk.Scrollbar(self.tree_frame)
        self.tree_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree_scroll_x = ttk.Scrollbar(self.tree_frame, orient=tk.HORIZONTAL)
        self.tree_scroll_x.pack(side=tk.BOTTOM, fill=tk.X)

        self.result_tree = ttk.Treeview(self.tree_frame,
                                        columns=("#", "Имя файла", "Путь", "Размер", "Дата изменения", "Порог", "НЮ"),
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
            "НЮ": {"width": 60, "anchor": "center"}
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

        # Статус бар
        self.status_var = tk.StringVar()
        self.status_bar = tk.Label(self.root, textvariable=self.status_var, bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)

        # Привязка событий
        self.result_tree.bind("<Double-1>", self.open_image)
        self.result_tree.bind("<<TreeviewSelect>>", self.show_preview)
        self.filter_var.trace_add('write', self.apply_filter)

    def convert_size(self, size_bytes):
        """Конвертирует размер файла в удобочитаемый формат"""
        for unit in ['Б', 'КБ', 'МБ', 'ГБ']:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} ТБ"

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
                    self.log_message(f"Ошибка перемещения {src_path}: {e}\n")

        self.status_var.set(f"Перемещено {moved_count} файлов в {target_folder}")
        messagebox.showinfo("Готово", f"Перемещено {moved_count} файлов")

    def sort_treeview_column(self, col, reverse):
        data = [(self.result_tree.set(k, col), k) for k in self.result_tree.get_children('')]

        # Преобразуем значения для числовых и текстовых столбцов
        def convert(value):
            try:
                return float(value.replace(",", "."))
            except:
                return value.lower()  # текст сравниваем нечувствительно к регистру

        data.sort(key=lambda t: convert(t[0]), reverse=reverse)

        for index, (_, k) in enumerate(data):
            self.result_tree.move(k, '', index)

        # Перепривязка заголовка для смены направления
        self.result_tree.heading(col, command=lambda: self.sort_treeview_column(col, not reverse))

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


    def update_file_list(self, batch):
        """Сохраняет и отображает список файлов"""
        self.all_files.extend(batch)  # Сохраняем в память

        self.root.after(0, lambda: [
            self.result_tree.insert("", "end", values=item) for item in batch
        ])


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

        if self.analysis_thread and self.analysis_thread.is_alive():
            self.log_message("Анализ уже выполняется\n")
            return

        model_name = self.model_type.get()
        self.log_message(f"🔧 Используется модель: {model_name}\n")

        self.stop_analysis = False
        self.analyze_button.config(text="Остановить")
        self.status_var.set("Анализ начат...")

        # Запуск анализа в отдельном потоке
        self.analysis_thread = threading.Thread(
            target=self.analyze_images,
            daemon=True
        )
        self.analysis_thread.start()
        self.move_button.config(state=tk.NORMAL)

    def get_cpu_cores(self):
        """Возвращает количество доступных логических ядер"""
        try:
            return os.cpu_count() or 4
        except Exception:
            return 4  # fallback

    def analyze_images(self):
        threshold = self.threshold_slider.get()
        items = self.result_tree.get_children()
        total_items = len(items)
        processed_count = 0
        max_threads = min(16, self.get_cpu_cores())

        self.log_message(f"▶ Доступно ядер: {self.get_cpu_cores()} | Используем потоков: {max_threads}\n")

        self.progress["value"] = 0
        self.progress["maximum"] = total_items
        self.progress.update()

        def process_item(item):
            nonlocal processed_count
            if self.stop_analysis:
                return

            img_path = self.result_tree.item(item)['values'][2]
            try:
                score, is_nude = self.is_nude_image(img_path, threshold)
                self.image_queue.put((
                    "update_item", item,
                    {
                        "Порог": f"{score:.4f}",
                        "НЮ": "✓" if is_nude else "✗",
                        "tag": "nude" if is_nude else "safe"
                    }
                ))
                self.image_queue.put(
                    ("log", f"{os.path.basename(img_path)}: {score:.4f} - {'НЮ' if is_nude else 'безопасно'}\n"))

            except Exception as e:
                self.image_queue.put(("log", f"Ошибка анализа {img_path}: {e}\n"))

            # Обновление прогресса
            processed_count += 1
            self.image_queue.put(("status", f"Анализ изображений... ({processed_count} / {total_items})"))
            self.image_queue.put(("progress", processed_count))

        with ThreadPoolExecutor(max_workers=max_threads) as executor:
            for item in items:
                executor.submit(process_item, item)

        nude_count = sum(1 for f in self.all_files if str(f[5]).strip().lower() == "ню")
        safe_count = sum(1 for f in self.all_files if str(f[5]).strip().lower() == "безопасно")
        total = len(self.all_files)
        unknown_count = total - nude_count - safe_count

        report = (
            "\n📊 Результаты анализа\n"
            f"┌──────────────────┬────────────┐\n"
            f"│ Всего            │ {total:<10}│\n"
            f"│ НЮ               │ {nude_count:<10}│\n"
            f"│ Безопасные       │ {safe_count:<10}│\n"
            f"│ Неопределённые   │ {unknown_count:<10}│\n"
            f"└──────────────────┴────────────┘\n"
        )

        self.image_queue.put(("log", report))

        self.image_queue.put(("status", "Анализ завершен"))
        self.image_queue.put(("analysis_complete", ""))

    def is_nude_image2(self, img_path, threshold):
        if not hasattr(self, 'n2') or not self.n2:
            self.load_model()

        try:
            score = self.n2.predict_image(img_path)
            return score, score >= threshold
        except Exception as e:
            self.log_message(f"Ошибка анализа {img_path}: {e}\n")
            return 0.0, False

    def is_nude_image(self, img_path, threshold):
        model_type = self.model_type.get().lower()

        try:
            if model_type == "yahoo":
                if not hasattr(self, 'n2'):
                    import opennsfw2
                    self.n2 = opennsfw2
                score = self.n2.predict_image(img_path)
                return score, score >= threshold

            elif model_type == "mobilenetv2":
                if not hasattr(self, 'mobilenet_model'):
                    import tensorflow as tf
                    self.mobilenet_model = tf.keras.applications.MobileNetV2(weights="imagenet")
                    self.log_message("MobileNetV2 загружена\n")
                # Здесь нужно добавить предобработку изображения и логику предсказания
                # (пример ниже)

            elif model_type == "tensorflow hub":
                if not hasattr(self, 'tfhub_model'):
                    import tensorflow as tf
                    import tensorflow_hub as hub
                    model_url = "https://tfhub.dev/google/openimages/v4/ssd/mobilenetv2/classification/4"
                    self.tfhub_model = hub.load(model_url)
                    self.log_message("TF Hub Detector загружен\n")
                # Предсказание через TF Hub (упрощённый пример)
                img = tf.io.read_file(img_path)
                img = tf.image.decode_jpeg(img, channels=3)
                img = tf.image.resize(img, [224, 224])
                img = tf.expand_dims(img, axis=0)
                predictions = self.tfhub_model(img)
                score = predictions.numpy()[0][1]  # Пример для бинарной классификации
                return score, score >= threshold

        except Exception as e:
            self.log_message(f"Ошибка модели {model_type}: {e}\n")
        return 0.0, False

    def preprocess_image(self, img_path):
        from tensorflow.keras.applications.mobilenet_v2 import preprocess_input
        import tensorflow as tf
        img = tf.io.read_file(img_path)
        img = tf.image.decode_jpeg(img, channels=3)
        img = tf.image.resize(img, [224, 224])
        img = preprocess_input(img)
        return tf.expand_dims(img, axis=0)

    def load_mobilenet_nsfw(self):
        """Загружает MobileNetV2 с NSFW-весами"""
        if not hasattr(self, 'mobilenet_nsfw'):
            import tensorflow as tf
            model = tf.keras.Sequential([
                tf.keras.applications.MobileNetV2(
                    input_shape=(224, 224, 3),
                    include_top=False,
                    weights="imagenet"
                ),
                tf.keras.layers.GlobalAveragePooling2D(),
                tf.keras.layers.Dense(1, activation="sigmoid")
            ])
            # Здесь можно загрузить свои веса (например, с Hugging Face)
            model.load_weights("path_to_nsfw_weights.h5")
            self.mobilenet_nsfw = model
            self.log_message("MobileNetV2 (NSFW) загружена\n")
        return self.mobilenet_nsfw

    def load_model(self):
        if not hasattr(self, 'n2') or not self.n2:
            import opennsfw2
            self.n2 = opennsfw2
            self.model_loaded = True
            self.log_message("Модель загружена\n")

    def process_queue(self):
        try:
            while True:
                task = self.image_queue.get_nowait()

                if isinstance(task, tuple):
                    if task[0] == "update_item":
                        item_id = task[1]
                        values = task[2]

                        # Обновляем Treeview
                        for col, val in values.items():
                            if col == "tag":
                                self.result_tree.item(item_id, tags=(val,))
                            else:
                                self.result_tree.set(item_id, col, val)

                        # Обновляем all_files
                        tree_values = list(self.result_tree.item(item_id, "values"))
                        path = tree_values[2]  # путь к файлу

                        for i, file_data in enumerate(self.all_files):
                            if file_data[2] == path:
                                tree_values[5] = values.get("Порог", file_data[5])
                                tree_values[6] = values.get("НЮ", file_data[6])
                                self.all_files[i] = tree_values
                                break

                    elif task[0] == "log":
                        self.log_console.insert(tk.END, task[1])
                        self.log_console.see(tk.END)

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


        except queue.Empty:
            pass

        self.root.after(100, self.process_queue)

    def apply_filter(self, *args):
        if getattr(self, "analysis_running", False):
            messagebox.showwarning("Анализ", "Нельзя менять фильтр во время анализа.")
            return

        filter_type = self.filter_var.get()

        # Очищаем текущее отображение
        for item in self.result_tree.get_children():
            self.result_tree.delete(item)

        # Отображаем подходящие строки
        for file_data in self.all_files:
            nude_status = file_data[6]  # 7-я колонка — "НЮ"

            if filter_type == "Только НЮ" and nude_status != "✓":
                continue
            elif filter_type == "Только безопасные" and nude_status != "✗":
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
            nude_status = self.result_tree.set(item, "НЮ")
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

    def show_preview(self, event):
        selected_item = self.result_tree.selection()
        if not selected_item:
            return

        img_path = self.result_tree.item(selected_item[0])['values'][2]
        self.current_image_path = img_path  # Сохраняем текущий путь

        try:
            # Очищаем предыдущее изображение
            self.preview_label.config(image=None)
            self.preview_label.image = None

            # Загружаем новое изображение
            img = Image.open(img_path)

            # Получаем размеры области превью
            preview_width = self.preview_frame.winfo_width() - 20
            preview_height = self.preview_frame.winfo_height() - 20

            # Вычисляем коэффициенты масштабирования
            width_ratio = preview_width / img.width
            height_ratio = preview_height / img.height
            scale_ratio = min(width_ratio, height_ratio)

            # Масштабируем с сохранением пропорций
            new_width = int(img.width * scale_ratio)
            new_height = int(img.height * scale_ratio)
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

            # Конвертируем для Tkinter
            photo = ImageTk.PhotoImage(img)

            # Отображаем изображение
            self.preview_label.config(image=photo)
            self.preview_label.image = photo

        except Exception as e:
            self.preview_label.config(image=None, text="Не удалось загрузить изображение")
            self.log_message(f"Ошибка загрузки превью: {e}\n")

    def resize_preview(self, event=None):
        if hasattr(self, 'current_image_path'):
            self.show_preview(None)

    def log_message(self, message):
        self.log_console.insert(tk.END, message)
        self.log_console.see(tk.END)
        self.log_console.update()
        # Автосохранение лога
        try:
            with open("../analyzer_nu.log", "a", encoding="utf-8") as f:
                f.write(message)
        except Exception as e:
            print(f"[Ошибка записи в лог-файл] {e}")


if __name__ == "__main__":
    root = tk.Tk()
    app = NSFWAnalyzerApp(root)
    root.mainloop()