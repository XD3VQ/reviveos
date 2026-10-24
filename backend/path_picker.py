"""Optional local native picker, launched only after a user clicks Browse."""
import json
import sys


def main():
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        if sys.argv[1] == "files":
            paths = list(filedialog.askopenfilenames(title="ReviveOS: choose files to back up", parent=root))
        else:
            path = filedialog.askdirectory(title="ReviveOS: choose a folder", parent=root, mustexist=True)
            paths = [path] if path else []
        root.destroy()
        print(json.dumps({"paths": paths}))
    except Exception:
        print(json.dumps({"error": "Native picker unavailable. Enter an absolute path manually (Linux may need python3-tk and a desktop session)."}))

if __name__ == "__main__":
    main()
