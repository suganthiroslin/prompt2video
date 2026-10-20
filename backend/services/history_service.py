"""Undo, redo, restore and auditable timeline snapshots."""
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from core.timeline import Timeline
from core.operations import OperationValidationError


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class HistoryService:
    def __init__(self, timeline: Timeline):
        self.timeline = timeline
        initial = self._snapshot()
        self._branch: list[dict[str, Any]] = [initial]
        self._index = 0
        self._archive: dict[int, dict[str, Any]] = {0: deepcopy(initial)}
        self._next_version = 1
        self.audit_log: list[dict[str, Any]] = []

    def _snapshot(self) -> dict[str, Any]:
        ops = self.timeline.get_operations()
        return {
            "version": self.timeline.version,
            "operations": ops,
            "timeline_hash": self.timeline.get_hash(),
            "created_at": _now(),
        }

    def _result(self, status: str, message: str) -> dict[str, Any]:
        return {
            "status": status, "message": message,
            "version": self.timeline.version,
            "timeline_hash": self.timeline.get_hash(),
            "can_undo": self.can_undo, "can_redo": self.can_redo,
        }

    @property
    def can_undo(self) -> bool:
        return self._index > 0

    @property
    def can_redo(self) -> bool:
        return self._index < len(self._branch) - 1

    def apply_operation(self, operation: dict[str, Any]) -> dict[str, Any]:
        try:
            added = self.timeline.add_operation(operation)
        except (OperationValidationError, TypeError, ValueError) as exc:
            return self._result("Rejected", str(exc))

        # New edits after undo start a new branch and permanently discard redo steps.
        self._branch = self._branch[: self._index + 1]
        self.timeline.version = self._next_version
        self._next_version += 1
        state = self._snapshot()
        self._branch.append(deepcopy(state))
        self._index = len(self._branch) - 1
        self._archive[state["version"]] = deepcopy(state)
        self.audit_log.append({"action": "apply", "operation": deepcopy(added), "version": state["version"], "at": _now()})
        result = self._result("Applied", "Instruction accepted as one history step.")
        result["operation"] = added
        return result

    def undo(self) -> dict[str, Any]:
        if not self.can_undo:
            return self._result("Needs clarification", "There is no edit to undo.")
        self._index -= 1
        state = self._branch[self._index]
        self.timeline.load_snapshot(state)
        self.audit_log.append({"action": "undo", "version": self.timeline.version, "at": _now()})
        return self._result("Applied", "Undid one instruction.")

    def redo(self) -> dict[str, Any]:
        if not self.can_redo:
            return self._result("Needs clarification", "There is no edit available to redo.")
        self._index += 1
        state = self._branch[self._index]
        self.timeline.load_snapshot(state)
        self.audit_log.append({"action": "redo", "version": self.timeline.version, "at": _now()})
        return self._result("Applied", "Redid one instruction.")

    def restore(self, version: int) -> dict[str, Any]:
        state = self._archive.get(int(version))
        if state is None:
            return self._result("Rejected", f"Timeline version {version} was not found.")
        self._branch = self._branch[: self._index + 1]
        self.timeline.load_snapshot({"version": self._next_version, "operations": deepcopy(state["operations"])})
        restored_as_version = self._next_version
        self._next_version += 1
        restored_state = self._snapshot()
        self._branch.append(deepcopy(restored_state))
        self._index = len(self._branch) - 1
        self._archive[restored_as_version] = deepcopy(restored_state)
        self.audit_log.append({"action": "restore", "restored_version": int(version), "version": restored_as_version, "at": _now()})
        result = self._result("Applied", f"Restored version {version} as a new history step.")
        result["restored_version"] = int(version)
        return result

    def export(self) -> dict[str, Any]:
        return {
            "active_index": self._index,
            "can_undo": self.can_undo,
            "can_redo": self.can_redo,
            "active_history": deepcopy(self._branch),
            "archived_versions": sorted(self._archive.keys()),
            "audit_log": deepcopy(self.audit_log),
        }
