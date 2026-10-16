"""Object storage port with a local filesystem adapter.

Keys are relative POSIX paths. Writes are atomic (temp file + rename) and
objects are treated as immutable once written. An S3-compatible adapter can
implement the same interface (pending, see docs/pending.md).
"""

from __future__ import annotations

import hashlib
import os
import shutil
import uuid
from pathlib import Path
from typing import BinaryIO, Protocol


class ObjectStorage(Protocol):
    def path(self, key: str) -> Path: ...
    def put_file(self, key: str, source: Path) -> None: ...
    def put_stream(self, key: str, stream: BinaryIO, max_bytes: int) -> tuple[int, str]: ...
    def exists(self, key: str) -> bool: ...
    def delete(self, key: str) -> None: ...
    def temp_path(self, suffix: str = "") -> Path: ...


class StorageError(Exception):
    pass


class LocalStorage:
    def __init__(self, base_dir: Path):
        self.base = base_dir.resolve()
        self.base.mkdir(parents=True, exist_ok=True)
        (self.base / "_tmp").mkdir(exist_ok=True)

    def path(self, key: str) -> Path:
        target = (self.base / key).resolve()
        if self.base not in target.parents:
            raise StorageError("Clave de almacenamiento inválida")
        return target

    def temp_path(self, suffix: str = "") -> Path:
        return self.base / "_tmp" / f"{uuid.uuid4().hex}{suffix}"

    def put_file(self, key: str, source: Path) -> None:
        target = self.path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + f".{uuid.uuid4().hex}.tmp")
        shutil.move(str(source), tmp)
        os.replace(tmp, target)

    def put_stream(self, key: str, stream: BinaryIO, max_bytes: int) -> tuple[int, str]:
        tmp = self.temp_path()
        digest = hashlib.sha256()
        size = 0
        try:
            with open(tmp, "wb") as out:
                while chunk := stream.read(1024 * 1024):
                    size += len(chunk)
                    if size > max_bytes:
                        raise StorageError(f"El archivo supera el máximo de {max_bytes // (1024 * 1024)} MB")
                    digest.update(chunk)
                    out.write(chunk)
            self.put_file(key, tmp)
        finally:
            tmp.unlink(missing_ok=True)
        return size, digest.hexdigest()

    def exists(self, key: str) -> bool:
        return self.path(key).exists()

    def delete(self, key: str) -> None:
        self.path(key).unlink(missing_ok=True)


_storage: LocalStorage | None = None


def get_storage() -> LocalStorage:
    global _storage
    if _storage is None:
        from feedstudio.config import get_settings

        _storage = LocalStorage(get_settings().storage_dir)
    return _storage


def set_storage(storage: LocalStorage) -> None:
    global _storage
    _storage = storage
