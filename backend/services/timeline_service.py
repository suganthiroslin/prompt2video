"""Application-facing prompt, timeline and history coordinator."""
from typing import Any
from core.timeline import Timeline
from services.history_service import HistoryService
from services.prompt_service import parse_prompt
from services.time_service import get_time_policy


class TimelineService:
    def __init__(self):
        self.timeline = Timeline()
        self.history_service = HistoryService(self.timeline)

    def process_prompt(self, prompt: str, source_duration: float | None = None) -> dict[str, Any]:
        parsed = parse_prompt(prompt)
        if parsed["status"] != "Applied":
            return {
                **self.get_timeline(),
                "status": parsed["status"], "message": parsed["message"],
                "operation": None,
            }
        # When source metadata is available, reject timestamps that exceed it
        # before adding anything to the timeline.
        if source_duration is not None:
            params = parsed["operation"].get("parameters", {})
            ranges = []
            if parsed["operation"].get("operation_type") == "reorder":
                ranges = [(item.get("start"), item.get("end")) for item in params.get("segments", [])]
            elif params.get("whole_source") is not True and "start" in params and "end" in params:
                ranges = [(params.get("start"), params.get("end"))]
            for start, end in ranges:
                if float(start) >= float(source_duration) or float(end) > float(source_duration) + 1e-3:
                    return {
                        **self.get_timeline(),
                        "status": "Rejected",
                        "message": f"The requested range {start:g}s–{end:g}s exceeds the uploaded video's {source_duration:.3f}s duration.",
                        "operation": None,
                    }
        result = self.history_service.apply_operation(parsed["operation"])
        if result["status"] == "Applied":
            result["message"] = parsed["message"]
            result["operation"] = result.get("operation", parsed["operation"])
        result["time_policy"] = get_time_policy()
        result["operations"] = self.timeline.get_operations()
        return result

    def get_timeline(self) -> dict[str, Any]:
        return {
            "status": "success", "version": self.timeline.version,
            "operations": self.timeline.get_operations(),
            "timeline_hash": self.timeline.get_hash(),
            "time_policy": get_time_policy(),
            "can_undo": self.history_service.can_undo,
            "can_redo": self.history_service.can_redo,
        }

    def undo(self) -> dict[str, Any]:
        result = self.history_service.undo()
        return {**result, "operations": self.timeline.get_operations(), "time_policy": get_time_policy()}

    def redo(self) -> dict[str, Any]:
        result = self.history_service.redo()
        return {**result, "operations": self.timeline.get_operations(), "time_policy": get_time_policy()}

    def restore(self, version: int) -> dict[str, Any]:
        result = self.history_service.restore(version)
        return {**result, "operations": self.timeline.get_operations(), "time_policy": get_time_policy()}

    def export_history(self) -> dict[str, Any]:
        return self.history_service.export()
