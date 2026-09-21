from __future__ import annotations

import tkinter as tk

from src.ui import NSFWAnalyzerApp


def main() -> None:
    root = tk.Tk()
    app = NSFWAnalyzerApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
