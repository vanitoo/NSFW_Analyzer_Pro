import os
import tkinter as tk


def convert_size(size_bytes):
    """Конвертирует размер файла в удобочитаемый формат"""
    for unit in ['Б', 'КБ', 'МБ', 'ГБ']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} ТБ"

def get_cpu_cores():
    """Возвращает количество доступных логических ядер"""
    import multiprocessing
    return multiprocessing.cpu_count()
    try:
        return os.cpu_count() or 4
    except Exception:
        return 4  # fallback

def log_message(message, console=None):
    if console:
        console.insert(tk.END, message)
        console.see(tk.END)
        console.update()
    try:
        with open("analyzer_nu.log", "a", encoding="utf-8") as f:
            f.write(message)
    except Exception as e:
        print(f"[Ошибка записи в лог-файл] {e}")
    print(message.strip())  # Вывод в консоль Python

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
