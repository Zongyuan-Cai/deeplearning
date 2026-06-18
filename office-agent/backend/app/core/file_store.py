from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from typing import Any, Dict, List

from app.core.config import settings


class FileStore:
    def __init__(self, upload_dir: str, output_dir: str):
        self.upload_dir = upload_dir
        self.output_dir = output_dir
        self.temp_dir = settings.TEMP_DIR
        self.cache_dir = settings.CACHE_DIR
        self.output_naming_style = settings.OUTPUT_NAMING_STYLE
        self.output_filename_max_len = max(16, int(settings.OUTPUT_FILENAME_MAX_LEN))

    def register_uploaded_file(
        self,
        *,
        task_id: str,
        file_id: str,
        filename: str,
        path: str,
        role: str | None = None,
        document_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        info = {
            "file_id": file_id,
            "filename": filename,
            "path": path,
            "role": role,
            "document_type": document_type,
            "size": os.path.getsize(path) if os.path.exists(path) else 0,
            "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "metadata": metadata or {},
        }
        records = self._read_task_metadata(task_id)
        records[file_id] = info
        self._write_task_metadata(task_id, records)
        return info

    def list_task_files(self, task_id: str) -> List[Dict[str, Any]]:
        task_dir = os.path.join(self.upload_dir, task_id)
        if not os.path.exists(task_dir):
            return []

        metadata = self._read_task_metadata(task_id)
        items = []
        for name in os.listdir(task_dir):
            path = os.path.join(task_dir, name)
            if os.path.isfile(path):
                record = {
                    "file_id": name,
                    "filename": name,
                    "path": path,
                    "size": os.path.getsize(path),
                }
                if isinstance(metadata.get(name), dict):
                    record.update(metadata[name])
                items.append(record)
        return items

    def get_file_info(self, task_id: str, file_id: str) -> Dict[str, Any]:
        path = os.path.join(self.upload_dir, task_id, file_id)
        if not os.path.exists(path):
            raise FileNotFoundError(path)

        metadata = self._read_task_metadata(task_id)
        stored = metadata.get(file_id) if isinstance(metadata.get(file_id), dict) else {}

        result = {
            "file_id": file_id,
            "filename": os.path.basename(path),
            "path": path,
            "size": os.path.getsize(path),
        }
        result.update(stored)
        return result

    def make_output_path(self, task_id: str, filename: str, output_tag: str | None = None) -> str:
        output_task_dir = os.path.join(self.output_dir, task_id)
        os.makedirs(output_task_dir, exist_ok=True)

        safe_name = self._sanitize_filename(filename)
        stem, ext = os.path.splitext(safe_name)
        if output_tag:
            stem = f"{stem}_{self._sanitize_filename(output_tag, allow_ext=False)}"
        stem = stem[: self.output_filename_max_len]

        if self.output_naming_style == "sequence":
            candidate = self._next_sequence_path(output_task_dir, stem, ext)
        else:
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            candidate = os.path.join(output_task_dir, f"{stem}_{ts}{ext}")
            if os.path.exists(candidate):
                candidate = self._next_sequence_path(output_task_dir, f"{stem}_{ts}", ext)
        return candidate

    def make_temp_path(self, task_id: str, filename: str) -> str:
        temp_task_dir = os.path.join(self.temp_dir, task_id)
        os.makedirs(temp_task_dir, exist_ok=True)
        safe_name = self._sanitize_filename(filename)
        return os.path.join(temp_task_dir, safe_name)

    def write_cache(self, task_id: str, key: str, value: Any) -> str:
        if not settings.ENABLE_FILESTORE_CACHE:
            raise RuntimeError("File store cache is disabled")

        cache_task_dir = os.path.join(self.cache_dir, task_id)
        os.makedirs(cache_task_dir, exist_ok=True)
        safe_key = self._sanitize_filename(key, allow_ext=False)
        path = os.path.join(cache_task_dir, f"{safe_key}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"created_at": time.time(), "value": value}, f, ensure_ascii=False, indent=2)
        return path

    def read_cache(self, task_id: str, key: str) -> Any:
        safe_key = self._sanitize_filename(key, allow_ext=False)
        path = os.path.join(self.cache_dir, task_id, f"{safe_key}.json")
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        return payload.get("value")

    def cleanup_expired(self) -> dict[str, int]:
        if not settings.CLEANUP_ENABLED:
            return {"temp_deleted": 0, "cache_deleted": 0}

        now = time.time()
        temp_deleted = self._cleanup_dir(self.temp_dir, now, settings.TEMP_FILE_TTL_SECONDS)
        cache_deleted = self._cleanup_dir(self.cache_dir, now, settings.CACHE_FILE_TTL_SECONDS)
        return {
            "temp_deleted": temp_deleted,
            "cache_deleted": cache_deleted,
        }

    def _cleanup_dir(self, root: str, now_ts: float, ttl_seconds: int) -> int:
        if not os.path.exists(root):
            return 0
        deleted = 0
        for current_root, _dirs, files in os.walk(root):
            for name in files:
                path = os.path.join(current_root, name)
                try:
                    mtime = os.path.getmtime(path)
                    if now_ts - mtime >= ttl_seconds:
                        os.remove(path)
                        deleted += 1
                except Exception:
                    continue
        return deleted

    def _task_metadata_path(self, task_id: str) -> str:
        return os.path.join(self.upload_dir, task_id, ".file_metadata.json")

    def _read_task_metadata(self, task_id: str) -> dict[str, Any]:
        path = self._task_metadata_path(task_id)
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _write_task_metadata(self, task_id: str, records: dict[str, Any]) -> None:
        task_dir = os.path.join(self.upload_dir, task_id)
        os.makedirs(task_dir, exist_ok=True)
        path = self._task_metadata_path(task_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

    def _next_sequence_path(self, output_dir: str, stem: str, ext: str) -> str:
        index = 1
        while True:
            candidate = os.path.join(output_dir, f"{stem}_{index:03d}{ext}")
            if not os.path.exists(candidate):
                return candidate
            index += 1

    @staticmethod
    def _sanitize_filename(filename: str, allow_ext: bool = True) -> str:
        raw = (filename or "output").strip()
        if not raw:
            raw = "output"
        cleaned = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]", "_", raw)
        if not allow_ext:
            cleaned = cleaned.replace(".", "_")
        cleaned = cleaned.strip("._")
        return cleaned or "output"