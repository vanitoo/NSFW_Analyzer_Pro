# ver 2.1.0

import sys
import tkinter as tk

import tensorflow as tf
from PIL import features

from ui import NSFWAnalyzerApp

print(f"Python version: {sys.version}")
print(f"TensorFlow version: {tf.__version__}")
print("Доступные устройства:", tf.config.list_physical_devices())
print("GPU устройства:", tf.config.list_physical_devices('GPU'))
print("Список поддерживаемых модулей:", features.get_supported_modules())

if __name__ == "__main__":
    root = tk.Tk()
    app = NSFWAnalyzerApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()
