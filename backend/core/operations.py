"""Structured edit operations and input validation."""
from copy import deepcopy
import math
from typing import Any

SUPPORTED_OPERATIONS = {"cut", "mute", "bleep", "caption", "effect", "speed", "reorder"}
SUPPORTED_EFFECTS = {"grayscale", "black_and_white", "brightness", "contrast", "saturation"}


class OperationValidationError(ValueError):
    """Raised when an edit cannot be represented safely."""


def _number(value: Any, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise OperationValidationError(f"{label} must be a number.") from None
    if not math.isfinite(result):
        raise OperationValidationError(f"{label} must be finite.")
    return result


def _range(params: dict[str, Any], label: str = "operation") -> None:
    start = _number(params.get("start"), f"{label} start time")
    end = _number(params.get("end"), f"{label} end time")
    if start < 0:
        raise OperationValidationError("Start time cannot be negative.")
    if end <= start:
        raise OperationValidationError("End time must be greater than start time.")
    params["start"], params["end"] = round(start, 6), round(end, 6)


def validate_operation(operation: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(operation, dict):
        raise OperationValidationError("An operation must be an object.")
    op_type = str(operation.get("operation_type", "")).strip().lower()
    if op_type not in SUPPORTED_OPERATIONS:
        raise OperationValidationError(f"Unsupported operation: {op_type or 'missing type'}.")
    raw = operation.get("parameters", {})
    if not isinstance(raw, dict):
        raise OperationValidationError("Operation parameters must be an object.")
    params = deepcopy(raw)

    if op_type == "reorder":
        segments = params.get("segments")
        if not isinstance(segments, list) or len(segments) < 2:
            raise OperationValidationError("Reorder needs at least two source-time ranges.")
        clean = []
        for segment in segments:
            if not isinstance(segment, dict):
                raise OperationValidationError("Each reorder segment needs start and end times.")
            item = {"start": segment.get("start"), "end": segment.get("end")}
            _range(item, "reorder segment")
            clean.append(item)
        params["segments"] = clean
    else:
        # Speed/effects may target the entire source without explicit start/end.
        whole_source_allowed = op_type in {"speed", "effect"} and params.get("whole_source") is True
        if whole_source_allowed:
            params.pop("start", None)
            params.pop("end", None)
        else:
            _range(params, op_type)

    if op_type == "speed":
        factor = _number(params.get("factor", 1), "speed factor")
        if not 0.25 <= factor <= 4.0:
            raise OperationValidationError("Speed factor must be between 0.25x and 4x.")
        params["factor"] = round(factor, 4)

    if op_type == "caption":
        text = params.get("text")
        if not isinstance(text, str) or not text.strip():
            raise OperationValidationError("A caption needs non-empty text.")
        if len(text) > 300:
            raise OperationValidationError("Caption text must be 300 characters or fewer.")
        params["text"] = text.strip()

    if op_type == "effect":
        name = str(params.get("name", "")).strip().lower().replace(" ", "_")
        if name not in SUPPORTED_EFFECTS:
            raise OperationValidationError("Unsupported effect. Use grayscale, brightness, contrast or saturation.")
        params["name"] = name
        if name == "brightness":
            value = _number(params.get("value", 0.15), "brightness value")
            if not -1 <= value <= 1:
                raise OperationValidationError("Brightness must be between -1 and 1.")
            params["value"] = round(value, 4)
        elif name == "contrast":
            value = _number(params.get("value", 1.2), "contrast value")
            if not 0 <= value <= 4:
                raise OperationValidationError("Contrast must be between 0 and 4.")
            params["value"] = round(value, 4)
        elif name == "saturation":
            value = _number(params.get("value", 1.2), "saturation value")
            if not 0 <= value <= 4:
                raise OperationValidationError("Saturation must be between 0 and 4.")
            params["value"] = round(value, 4)

    if op_type == "bleep":
        frequency = _number(params.get("frequency", 1000), "bleep frequency")
        if not 100 <= frequency <= 4000:
            raise OperationValidationError("Bleep frequency must be between 100 and 4000 Hz.")
        params["frequency"] = round(frequency, 2)

    return {"operation_type": op_type, "parameters": params}
