"""Simple on-disk JSON cache to avoid repeat Wikimedia API hits."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any


class DiskCache:
    def __init__(self, root: Path, *, ttl_sec: float = 7 * 24 * 3600):
        self.root = root
        self.ttl_sec = ttl_sec
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, namespace: str, key: str) -> Path:
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
        folder = self.root / namespace
        folder.mkdir(parents=True, exist_ok=True)
        return folder / f"{digest}.json"

    def get(self, namespace: str, key: str) -> Any | None:
        path = self._path(namespace, key)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if time.time() - float(payload.get("saved_at", 0)) > self.ttl_sec:
            return None
        return payload.get("value")

    def set(self, namespace: str, key: str, value: Any) -> None:
        path = self._path(namespace, key)
        path.write_text(
            json.dumps({"saved_at": time.time(), "value": value}, indent=None),
            encoding="utf-8",
        )
