import tkinter as tk
from tkinter import ttk, filedialog
import threading
import queue
from PIL import Image, ImageTk
import os

from analyzer_worker import AnalyzerWorker
from utils import log_message


class NSFWAnalyzerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("NSFW Analyzer")

        self.image_queue = queue.Queue()

        # --- Верхняя панель ---
        top_frame = tk.Frame(self.root)
        top_frame.pack(fill=tk.X, pady=5)

        self.scan_button = tk.Button(top_frame, text="Сканировать папку", command=self.select_folder)
        self.scan_button.pack(side=tk.LEFT, padx=5)

        self.analyze_button = tk.Button(top_frame, text="Анализировать", command=self.start_analysis)
        self.analyze_button.pack(side=tk.LEFT, padx=5)

        tk.Label(top_frame, text="Модель:").pack(side=tk.LEFT, padx=5)
        self.model_type = ttk.Combobox(top_frame,
                                       values=["yahoo", "mobilenet", "nsfw hub", "gantman"],
                                       state="readonly")
        self.model_type.current(0)
        self.model_type.pack(side=tk.LEFT, padx=5)

        tk.Label(top_frame, text="Порог:").pack(side=tk.LEFT, padx=5)
        self.threshold_slider = tk.Scale(top_frame, from_=0, to=1, resolution=0.01,
                                         orient=tk.HORIZONTAL, length=120)
        self.threshold_slider.set(0.5)
        self.threshold_slider.pack(side=tk.LEFT, padx=5)

        tk.Label(top_frame, text="Фильтр:").pack(side=tk.LEFT, padx=5)
        self.filter_combobox = ttk.Combobox(top_frame,
                                            values=["Все", "Только НЮ", "Только безопасные"],
                                            state="readonly")
        self.filter_combobox.current(0)
        self.filter_combobox.pack(side=tk.LEFT, padx=5)

        # --- Таблица результатов ---
        columns = ("index", "name", "path", "size", "mtime", "score", "mark")
        self.result_tree = ttk.Treeview(self.root, columns=columns, show="headings")
        self.result_tree.pack(fill=tk.BOTH, expand=True)

        for col, text, width in [
            ("index", "#", 40),
            ("name", "Имя файла", 200),
            ("path", "Путь", 400),
            ("size", "Размер", 100),
            ("mtime", "Дата изменения", 150),
            ("score", "Порог", 80),
            ("mark", "НЮ", 60),
        ]:
            self.result_tree.heading(col, text=text)
            self.result_tree.column(col, width=width)

        self.result_tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        # --- Лог ---
        self.log_console = tk.Text(self.root, height=8)
        self.log_console.pack(fill=tk.X, padx=5, pady=5)

        # --- Статус и прогресс ---
        status_frame = tk.Frame(self.root)
        status_frame.pack(side="bottom", fill="x")

        self.status_var = tk.StringVar()
        self.status_bar = tk.Label(status_frame, textvariable=self.status_var,
                                   bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        self.progress = ttk.Progressbar(status_frame, mode="determinate",
                                        length=300, maximum=100)
        self.progress.pack(side=tk.RIGHT, padx=5)

        # --- Превью ---
        self.preview_label = tk.Label(self.root, text="Превью не выбрано", anchor="center")
        self.preview_label.pack(fill=tk.BOTH, expand=False, pady=5)

        # --- Состояния ---
        self.stop_analysis = False
        self.running = True

        # --- Воркёр ---
        self.worker = AnalyzerWorker(log_console=self.log_console)
        self.worker.image_queue = self.image_queue

        # Очередь обработки
        self.start_queue_processing()

    # ================= UI-методы =================
    def select_folder(self):
        folder_path = filedialog.askdirectory()
        if folder_path:
            threading.Thread(target=self.worker.scan_folder_async,
                             args=(folder_path,), daemon=True).start()

    def start_analysis(self):
        # блокируем элементы
        self.analyze_button.config(state=tk.DISABLED)
        self.filter_combobox.config(state=tk.DISABLED)
        self.threshold_slider.config(state=tk.DISABLED)
        self.model_type.config(state=tk.DISABLED)
        threading.Thread(target=self.worker.analyze_images, daemon=True).start()

    def on_tree_select(self, event):
        selected = self.result_tree.selection()
        if not selected:
            return
        item_id = selected[0]
        path = self.result_tree.item(item_id)['values'][2]
        self.show_preview(path)

    def show_preview(self, img_path):
        try:
            img = Image.open(img_path)
            img.thumbnail((400, 400))
            tk_img = ImageTk.PhotoImage(img)
            self.preview_label.config(image=tk_img, text="")
            self.preview_label.image = tk_img
        except Exception as e:
            self.preview_label.config(image="", text="Не удалось загрузить изображение")
            log_message(f"⚠ Ошибка предпросмотра {img_path}: {e}\n")

    # ================= Очередь =================
    def start_queue_processing(self):
        self.root.after(100, self.process_queue)

    def process_queue(self):
        try:
            while True:
                msg = self.image_queue.get_nowait()
                mtype = msg[0]
                if mtype == "log":
                    self.log_console.insert(tk.END, msg[1])
                    self.log_console.see(tk.END)
                elif mtype == "status":
                    self.status_var.set(msg[1])
                elif mtype == "progress":
                    self.progress["value"] = msg[1]
                elif mtype == "update_item":
                    item_id, values = msg[1], msg[2]
                    self.result_tree.set(item_id, "score", values["Порог"])
                    self.result_tree.set(item_id, "mark", values["НЮ"])
                    self.result_tree.item(item_id, tags=(values["tag"],))
                elif mtype == "scan_complete":
                    self.status_var.set(f"Загружено {msg[1]} изображений")
                    self.progress["value"] = 0
                elif mtype == "analysis_complete":
                    self.status_var.set("Анализ завершён")
                    self.progress["value"] = 0
                    # разблокируем элементы
                    self.analyze_button.config(state=tk.NORMAL)
                    self.filter_combobox.config(state=tk.NORMAL)
                    self.threshold_slider.config(state=tk.NORMAL)
                    self.model_type.config(state=tk.NORMAL)
        except queue.Empty:
            pass
        self.root.after(100, self.process_queue)


if __name__ == "__main__":
    root = tk.Tk()
    app = NSFWAnalyzerApp(root)
    root.mainloop()
