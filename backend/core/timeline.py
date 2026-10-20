"""Deterministic timeline with immutable source-time anchors."""
from copy import deepcopy
from typing import Any
from core.hashing import timeline_hash
from core.models import EditOperation, TimelineSnapshot
from core.operations import validate_operation


class Timeline:
    def __init__(self):
        self._operations: list[dict[str, Any]] = []
        self.version = 0

    def add_operation(self, operation: dict[str, Any] | EditOperation) -> dict[str, Any]:
        raw = operation.to_dict() if isinstance(operation, EditOperation) else deepcopy(operation)
        normalized = validate_operation(raw)
        item = EditOperation(
            operation_type=normalized["operation_type"],
            parameters=normalized["parameters"],
        )
        if isinstance(raw, dict):
            if raw.get("operation_id"):
                item.operation_id = str(raw["operation_id"])
            if raw.get("created_at"):
                item.created_at = str(raw["created_at"])
        value = item.to_dict()
        self._operations.append(value)
        self.version += 1
        return deepcopy(value)

    def get_operations(self) -> list[dict[str, Any]]:
        return deepcopy(self._operations)

    def get_hash(self) -> str:
        return timeline_hash(self._operations)

    def snapshot(self) -> TimelineSnapshot:
        ops = self.get_operations()
        return TimelineSnapshot(self.version, ops, timeline_hash(ops))

    def load_snapshot(self, snapshot: dict[str, Any] | TimelineSnapshot) -> None:
        if isinstance(snapshot, TimelineSnapshot):
            self.version = int(snapshot.version)
            self._operations = deepcopy(snapshot.operations)
        else:
            self.version = int(snapshot.get("version", 0))
            self._operations = deepcopy(snapshot.get("operations", []))

    def clear(self) -> None:
        self._operations = []
        self.version += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "operations": self.get_operations(),
            "timeline_hash": self.get_hash(),
            "time_policy": "original_source_time",
        }
