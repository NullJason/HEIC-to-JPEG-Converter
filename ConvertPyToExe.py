# if you don't trust the release, here is a complimentary py to exe converter but at this point you may as well just run the original python file itself.

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


# ---------------------------
# Dependency bootstrap
# ---------------------------

def ensure_package(module_name: str, pip_name: str | None = None) -> None:
    if importlib.util.find_spec(module_name) is not None:
        return

    pkg = pip_name or module_name
    print(f"Installing missing dependency: {pkg}")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", pkg])


ensure_package("PyInstaller", "pyinstaller")

# ---------------------------
# Helpers
# ---------------------------

def format_bytes(num: int) -> str:
    if num >= 1024 ** 3:
        return f"{num / (1024 ** 3):.2f} GB"
    if num >= 1024 ** 2:
        return f"{num / (1024 ** 2):.2f} MB"
    if num >= 1024:
        return f"{num / 1024:.2f} KB"
    return f"{num} B"


def prompt_yes_no(message: str, default: bool = False) -> bool:
    default_hint = "Y/n" if default else "y/N"

    if sys.stdin.isatty():
        while True:
            try:
                answer = input(f"{message} [{default_hint}]: ").strip().lower()
            except EOFError:
                return default

            if not answer:
                return default
            if answer in {"y", "yes"}:
                return True
            if answer in {"n", "no"}:
                return False
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        result = messagebox.askyesno("Py to EXE", message)
        root.destroy()
        return bool(result)
    except Exception:
        return default


def prompt_text(message: str, default: str = "") -> str:
    if sys.stdin.isatty():
        try:
            raw = input(f"{message}{' [' + default + ']' if default else ''}: ").strip()
            return raw or default
        except EOFError:
            return default

    try:
        import tkinter as tk
        from tkinter import simpledialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        raw = simpledialog.askstring("Py to EXE", message, initialvalue=default)
        root.destroy()
        return (raw or default).strip()
    except Exception:
        return default


def pick_file_or_folder() -> Path | None:
    if len(sys.argv) > 1:
        return Path(sys.argv[1].strip().strip('"'))

    if sys.stdin.isatty():
        raw = input("Enter a .py file path or a folder path (blank = current directory): ").strip()
        return Path(raw.strip('"')) if raw else Path.cwd()

    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)

        use_cwd = messagebox.askyesno(
            "Py to EXE",
            "No path was provided.\nUse the current directory?"
        )
        if use_cwd:
            root.destroy()
            return Path.cwd()

        py_file = filedialog.askopenfilename(
            title="Select a Python file",
            filetypes=[("Python files", "*.py"), ("All files", "*.*")]
        )
        if py_file:
            root.destroy()
            return Path(py_file)

        folder = filedialog.askdirectory(title="Select a folder")
        root.destroy()
        return Path(folder) if folder else None
    except Exception:
        return None


def resolve_path(raw: Path) -> Path:
    p = raw.expanduser()
    if not p.is_absolute():
        p = (Path.cwd() / p).resolve()
    return p


def suggest_path(raw: str) -> Path | None:
    raw = raw.strip().strip('"').strip("./\\").lower()
    if not raw:
        return None

    cwd = Path.cwd()
    candidates = []

    try:
        for p in cwd.rglob("*"):
            if raw in p.name.lower():
                candidates.append(p)
    except Exception:
        return None

    if not candidates:
        return None

    def score(p: Path) -> tuple[int, int]:
        return (len(p.name), len(str(p)))

    return sorted(candidates, key=score)[0]


def choose_entry_script(folder: Path) -> Path | None:
    py_files = sorted(
        [p for p in folder.glob("*.py") if p.is_file()],
        key=lambda p: p.name.lower()
    )

    if not py_files:
        return None

    if len(py_files) == 1:
        return py_files[0]

    print(f"\nMultiple Python files found in: {folder}")
    for i, p in enumerate(py_files, 1):
        print(f"{i}. {p.name}")

    while True:
        choice = prompt_text("Select the entry script number", "1")
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(py_files):
                return py_files[idx - 1]
        print("Invalid selection.")


def resolve_source() -> Path:
    while True:
        raw = pick_file_or_folder()
        if raw is None:
            print("No path selected.")
            continue

        p = resolve_path(raw)

        if p.exists():
            if p.is_file():
                if p.suffix.lower() != ".py":
                    print(f"Selected file is not a .py file: {p}")
                    continue
                return p

            if p.is_dir():
                entry = choose_entry_script(p)
                if entry is None:
                    print(f"No .py files found in: {p}")
                    continue
                return entry

        suggestion = suggest_path(str(raw))
        if suggestion is not None:
            if prompt_yes_no(f"Path not found.\nDid you mean:\n{suggestion}\nUse it?", default=True):
                if suggestion.is_file() and suggestion.suffix.lower() == ".py":
                    return suggestion
                if suggestion.is_dir():
                    entry = choose_entry_script(suggestion)
                    if entry is not None:
                        return entry

        retry = prompt_yes_no("Invalid path.\nTry again?", default=True)
        if not retry:
            raise SystemExit(0)


def confirm_build(script: Path) -> bool:
    msg = (
        f"Build EXE from:\n{script}\n\n"
        f"Output name: {script.stem}.exe\n"
        f"PyInstaller: onefile + console"
    )
    return prompt_yes_no(msg, default=True)


def build(script: Path) -> Path:
    dist_dir = script.parent / "dist"
    build_dir = script.parent / "build"

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--console",
        "--clean",
        "--name",
        script.stem,
        str(script),
    ]

    subprocess.run(cmd, check=True, cwd=str(script.parent))

    exe_path = dist_dir / f"{script.stem}.exe"
    return exe_path


def post_build_menu() -> str:
    while True:
        print("\nOptions:")
        print("1. Exit")
        print("2. Build another file / directory")

        choice = prompt_text("Select option", "1").strip()
        if choice == "1":
            return "exit"
        if choice == "2":
            return "again"
        print("Invalid option.")


def main() -> int:
    while True:
        script = resolve_source()

        if not confirm_build(script):
            if post_build_menu() == "again":
                continue
            return 0

        try:
            exe_path = build(script)
            print(f"\nBuilt: {exe_path}")
        except subprocess.CalledProcessError as e:
            print(f"Build failed: {e}")
        except Exception as e:
            print(f"Unexpected error: {e}")

        if post_build_menu() != "again":
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
