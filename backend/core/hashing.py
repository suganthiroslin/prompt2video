"""Canonical hashes for reproducible timelines and media files."""

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


def sha256_file(file_path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_operation(operation: dict[str, Any]) -> dict[str, Any]:
    """Exclude volatile IDs/timestamps; include only edit meaning."""
    canonical = {
        "operation_type": str(operation.get("operation_type", "")),
        "parameters": operation.get("parameters", {}),
    }
    anchor = operation.get("anchor")
    if anchor is not None:
        canonical["anchor"] = anchor
    return canonical


def timeline_hash(operations: Iterable[dict[str, Any]]) -> str:
    normalized = [canonical_operation(op) for op in operations]
    encoded = json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
