from __future__ import annotations

import os
from typing import Any

from fastapi import UploadFile


async def persist_uploaded_files(
    files: list[UploadFile],
    *,
    upload_dir: str,
) -> list[dict[str, Any]]:
    os.makedirs(upload_dir, exist_ok=True)
    file_infos: list[dict[str, Any]] = []
    for idx, file in enumerate(files, start=1):
        filename = file.filename or f"upload_{idx}"
        save_path = os.path.join(upload_dir, filename)
        with open(save_path, "wb") as out:
            out.write(await file.read())
        file_infos.append(
            {
                "file_id": filename,
                "filename": filename,
                "path": save_path,
            }
        )
    return file_infos

