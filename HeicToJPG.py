from __future__ import annotations

import os
import sys
from pathlib import Path
import subprocess
import importlib.util


def ensure_package(module_name: str, pip_name: str | None = None):
    if importlib.util.find_spec(module_name) is not None:
        return

    pkg = pip_name or module_name
    print(f"Installing missing dependency: {pkg}")

    subprocess.check_call([
        sys.executable,
        "-m",
        "pip",
        "install",
        "--upgrade",
        pkg
    ])


ensure_package("PIL", "pillow")
ensure_package("pillow_heif")

# imports pillow, python library for imaging.
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

register_heif_opener()

GI_B = 1024 ** 3
MI_B = 1024 ** 2

OVERWRITE_ALL = None  # None | True (replace all) | False (skip all)


def format_bytes(num: int) -> str:
    if num >= GI_B:
        return f"{num / GI_B:.2f} GB"
    if num >= MI_B:
        return f"{num / MI_B:.2f} MB"
    return f"{num} B"


def is_heic(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() == ".heic"


def prompt_yes_no(message: str) -> bool:
    if sys.stdin.isatty():
        try:
            answer = input(f"{message} [y/N]: ").strip().lower()
            return answer in {"y", "yes"}
        except EOFError:
            return False

    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        result = messagebox.askyesno("HEIC to JPG", message)
        root.destroy()
        return bool(result)
    except Exception:
        return False

def resolve_overwrite(path: Path) -> bool:
    """
    returns True = write/overwrite
            False = skip
    """
    global OVERWRITE_ALL

    if OVERWRITE_ALL is True:
        return True
    if OVERWRITE_ALL is False:
        return False

    msg = f"File exists:\n{path}\n\nReplace it?"

    # CLI fallback
    if sys.stdin.isatty():
        while True:
            print("\nConflict detected:", path)
            print("[r] replace")
            print("[s] skip")
            print("[ra] replace all")
            print("[sa] skip all")

            choice = input("Select: ").strip().lower()

            if choice == "r":
                return True
            if choice == "s":
                return False
            if choice == "ra":
                OVERWRITE_ALL = True
                return True
            if choice == "sa":
                OVERWRITE_ALL = False
                return False

    # GUI fallback
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()

        res = messagebox.askyesnocancel(
            "File exists",
            f"{path}\n\nYes = replace\nNo = skip\nCancel = skip all"
        )

        root.destroy()

        if res is True:
            return True
        if res is False:
            return False

        OVERWRITE_ALL = False
        return False

    except Exception:
        return False


def resolve_path(raw: str) -> Path | None:
    raw = raw.strip().strip('"')

    p = Path(raw)

    # normalize relative forms
    if not p.is_absolute():
        p = (Path.cwd() / p).resolve()

    return p


def suggest_path(raw: str) -> Path | None:
    cwd = Path.cwd()
    candidates = list(cwd.rglob("*"))

    raw_lower = raw.lower().strip("./\\").strip()

    matches = [p for p in candidates if raw_lower in p.name.lower()]

    if not matches:
        return None

    return sorted(matches, key=lambda x: len(x.name))[0]


def prompt_for_path() -> Path | None:
    if len(sys.argv) > 1:
        return Path(sys.argv[1].strip().strip('"'))

    if sys.stdin.isatty():
        raw = input("Enter a file/folder path, or press Enter to use the current directory: ").strip()
        return Path(raw.strip('"')) if raw else Path.cwd()

    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, simpledialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        cwd = Path.cwd()
        total_bytes, heic_bytes, heic_files = scan_folder(cwd)
        summary = (
            "No path was provided."
            f"Total data: {format_bytes(total_bytes)}\n"
            f"HEIC data: {format_bytes(heic_bytes)}\n"
            f"HEIC files: {len(heic_files)}\n\n"
            f"Convert files in current directory ({cwd})?"
        )
        use_cwd = messagebox.askyesno(
            "HEIC to JPG",
            summary
        )
        if use_cwd:
            root.destroy()
            return Path.cwd()

        raw = simpledialog.askstring(
            "HEIC to JPG",
            "Enter a file or folder path:",
            initialvalue=str(Path.cwd()),
        )
        if raw and raw.strip():
            root.destroy()
            return Path(raw.strip().strip('"'))

        file_path = filedialog.askopenfilename(
            title="Select a HEIC file",
            filetypes=[("HEIC files", "*.heic"), ("All files", "*.*")],
        )
        if file_path:
            root.destroy()
            return Path(file_path)

        folder_path = filedialog.askdirectory(title="Select a folder")
        root.destroy()
        return Path(folder_path) if folder_path else None
    except Exception:
        return None


def convert_one_file(src: Path) -> Path | None:
    if not is_heic(src):
        print(f"Skipping non-HEIC file: {src}")
        return None

    out = src.with_suffix(".jpg")

    if out.exists():
        if not resolve_overwrite(out):
            print(f"Skipped: {src}")
            return None

    try:
        with Image.open(src) as img:
            img = ImageOps.exif_transpose(img)

            if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                rgba = img.convert("RGBA")
                background = Image.new("RGB", rgba.size, (255, 255, 255))
                background.paste(rgba, mask=rgba.getchannel("A"))
                rgb = background
            else:
                rgb = img.convert("RGB")

            rgb.save(out, format="JPEG", quality=95, optimize=True)

            # supposed to prevent edge case portrait orientation and palette modes inconsistency, not tested.
            # img = ImageOps.exif_transpose(img)

            # if img.mode not in ("RGB", "RGBA"):
            #     img = img.convert("RGBA")

            # if img.mode == "RGBA":
            #     background = Image.new("RGB", img.size, (255, 255, 255))
            #     background.paste(img, mask=img.getchannel("A"))
            #     img = background
            # else:
            #     img = img.convert("RGB")

            # img.save(out, format="JPEG", quality=95, optimize=True)

        print(f"Saved: {out}")
        return out
    except Exception as e:
        print(f"Failed: {src} -> {e}")
        return None


def scan_folder(folder: Path) -> tuple[int, int, list[Path]]:
    total_bytes = 0
    heic_bytes = 0
    heic_files: list[Path] = []

    for root, _, files in os.walk(folder):
        root_path = Path(root)
        for name in files:
            p = root_path / name
            try:
                size = p.stat().st_size
            except OSError:
                continue

            total_bytes += size
            if p.suffix.lower() == ".heic":
                heic_bytes += size
                heic_files.append(p)

    return total_bytes, heic_bytes, heic_files


def convert_folder(folder: Path) -> tuple[int, int, list[Path]]:
    total_bytes, heic_bytes, heic_files = scan_folder(folder)

    converted_paths = []

    summary = (
        f"Directory: {folder}\n"
        f"Total data: {format_bytes(total_bytes)}\n"
        f"HEIC data: {format_bytes(heic_bytes)}\n"
        f"HEIC files: {len(heic_files)}"
    )
    
    if total_bytes > GI_B:
        warning = (
            f"{summary}\n\n"
            f"WARNING: this directory contains {total_bytes / GI_B:.2f} gigabytes of data, "
            f"{heic_bytes / MI_B:.2f} mb of which are heic files, are you sure?"
        )
    else:
        warning = f"{summary}\n\nProceed with conversion?"

    
    if not prompt_yes_no(warning):
        print("Cancelled.")
        return 0, 0, []

    converted = 0
    failed = 0

    for src in heic_files:
        result = convert_one_file(src)
        if result:
            converted += 1
            converted_paths.append(result)
        else:
            failed += 1


    print(f"Done. Converted: {converted}, Failed: {failed}, HEIC found: {len(heic_files)}")
    return converted, failed, converted_paths


def post_run_menu(last_folder: Path | None, converted_files: list[Path]):
    while True:
        print("\nOptions:")
        print("1. Exit")
        print("2. Delete original HEIC files")
        print("3. Convert more files / directory")

        choice = input("Select option: ").strip()

        if choice == "1":
            return None

        elif choice == "2":
            if not converted_files:
                print("No converted files tracked.")
                continue

            if not prompt_yes_no("Delete original HEIC files?"):
                continue

            deleted = 0
            for jpg in converted_files:
                heic = jpg.with_suffix(".heic")
                try:
                    if heic.exists():
                        heic.unlink()
                        deleted += 1
                except Exception as e:
                    print(f"Failed to delete {heic}: {e}")

            print(f"Deleted {deleted} HEIC files.")

        elif choice == "3":
            return "restart"

        else:
            print("Invalid option.")


def main() -> int:
    raw = prompt_for_path()
    if raw is None:
        print("No path selected.")
        return 1

    target = resolve_path(str(raw))

    if target is None or not target.exists():
        suggestion = suggest_path(str(raw))

        if suggestion and prompt_yes_no(f"Path not found.\nDid you mean:\n{suggestion}?"):
            target = suggestion
        else:
            print(f"Invalid path: {raw}")
            return 1
        
    if target is None:
        print("No path selected.")
        return 1

    target = target.expanduser()

    if not target.exists():
        print(f"Path not found: {target}")
        return 1

    if target.is_file():
        if not is_heic(target):
            print(f"Selected file is not a .heic file: {target}")
            return 1

        if not prompt_yes_no(f"Convert this file to JPG?\n{target}"):
            print("Cancelled.")
            return 0

        result = convert_one_file(target)
        converted_paths = [result] if result else []
        post = post_run_menu(None, converted_paths)

        if post == "restart":
            return main()

        return 0 if result else 1


    if target.is_dir():
        converted, failed, converted_paths = convert_folder(target)
        post = post_run_menu(target, converted_paths)

        if post == "restart":
            return main()

        return 0


    print(f"Unsupported path: {target}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
