"""Optional JSON persistence for exported timeline histories."""
import json
import os
import tempfile
from pathlib import Path
from typing import Any
from config import Config


class HistoryStore:
    def __init__(self, root: str | Path | None = None):
        Config.ensure_directories()
        self.root = Path(root or Config.HISTORY_FOLDER)
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, session_id: str, history: dict[str, Any]) -> Path:
        target = self.root / f"{session_id}.json"
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.root, delete=False) as handle:
            json.dump(history, handle, indent=2, sort_keys=True)
            temp_name = handle.name
        os.replace(temp_name, target)
        return target

    def load(self, session_id: str) -> dict[str, Any]:
        target = self.root / f"{session_id}.json"
        if not target.is_file():
            raise FileNotFoundError(f"History not found for session {session_id}")
        with target.open("r", encoding="utf-8") as handle:
            return json.load(handle)
