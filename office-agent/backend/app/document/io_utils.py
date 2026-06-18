from __future__ import annotations

import os
from pathlib import Path


def ensure_parent_dir(file_path: str) -> None:
    parent = Path(file_path).expanduser().resolve().parent
    parent.mkdir(parents=True, exist_ok=True)


def existing_nonempty_file(file_path: str | None) -> bool:
    if not file_path:
        return False
    path = Path(file_path)
    return path.is_file() and path.stat().st_size > 0


def validate_input_file(file_path: str) -> tuple[bool, str]:
    path = Path(file_path)
    if not path.exists():
        return False, f"Input file does not exist: {file_path}"
    if not path.is_file():
        return False, f"Input path is not a file: {file_path}"
    if path.stat().st_size <= 0:
        return False, f"Input file is empty: {file_path}"
    return True, ""


def next_available_path(file_path: str) -> str:
    base, ext = os.path.splitext(file_path)
    index = 1
    candidate = f"{base}_{index}{ext}"
    while os.path.exists(candidate):
        index += 1
        candidate = f"{base}_{index}{ext}"
    return candidate


def safe_output_path(source_file_path: str, output_path: str, *, avoid_overwrite: bool = True) -> tuple[str, bool]:
    source_abs = os.path.abspath(source_file_path)
    candidate = os.path.abspath(output_path)
    avoided = False
    if avoid_overwrite and (candidate == source_abs or os.path.exists(candidate)):
        candidate = next_available_path(candidate)
        avoided = True
    if candidate == source_abs:
        candidate = next_available_path(candidate)
        avoided = True
    ensure_parent_dir(candidate)
    return candidate, avoided
