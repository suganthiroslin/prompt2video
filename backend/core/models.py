"""Typed data models used by the editing pipeline."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class OriginalMedia:
    file_path: str
    sha256: str
    duration: float
    fps: float
    width: int
    height: int
    has_audio: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path, "sha256": self.sha256,
            "duration": self.duration, "fps": self.fps,
            "width": self.width, "height": self.height,
            "has_audio": self.has_audio,
        }


@dataclass
class EditOperation:
    operation_type: str
    parameters: dict[str, Any]
    operation_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "operation_type": self.operation_type,
            "parameters": self.parameters,
            "operation_id": self.operation_id,
            "created_at": self.created_at,
        }
        params = self.parameters or {}
        if "start" in params and "end" in params:
            result["anchor"] = {
                "coordinate_system": "original_source_time",
                "start": float(params["start"]),
                "end": float(params["end"]),
            }
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "EditOperation":
        return cls(
            operation_type=value["operation_type"],
            parameters=dict(value.get("parameters", {})),
            operation_id=value.get("operation_id") or str(uuid4()),
            created_at=value.get("created_at") or utc_now(),
        )


@dataclass
class TimelineSnapshot:
    version: int
    operations: list[dict[str, Any]]
    timeline_hash: str


@dataclass
class EditSession:
    session_id: str = field(default_factory=lambda: str(uuid4()))
    original: Optional[OriginalMedia] = None
    history: list[dict[str, Any]] = field(default_factory=list)
    history_index: int = 0
    time_policy: str = "original_source_time"
    created_at: str = field(default_factory=utc_now)
