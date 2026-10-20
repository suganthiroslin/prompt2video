"""Deterministic rule-based translation from natural language to edit operations."""
import re
from typing import Any
from core.operations import OperationValidationError, validate_operation
from services.time_service import parse_time

_TIME = r"(?:\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?|\d+(?:\.\d+)?)(?:\s*(?:seconds?|secs?|sec|s)\b)?"
_RANGE_RE = re.compile(rf"(?P<start>{_TIME})\s*(?:to|until|through|–|—|-)\s*(?P<end>{_TIME})", re.IGNORECASE)


def _ranges(text: str) -> list[tuple[float, float]]:
    found = []
    for match in _RANGE_RE.finditer(text):
        try:
            start, end = parse_time(match.group("start")), parse_time(match.group("end"))
        except ValueError:
            continue
        found.append((start, end))
    return found


def _one_range(text: str) -> tuple[float, float] | None:
    ranges = _ranges(text)
    return ranges[0] if ranges else None


def _point_after_at(text: str) -> float | None:
    match = re.search(rf"\bat\s+(?P<time>{_TIME})", text, re.IGNORECASE)
    if not match:
        return None
    try:
        return parse_time(match.group("time"))
    except ValueError:
        return None


def _response(status: str, message: str, operation: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"status": status, "message": message, "operation": operation}


def _validated(operation: dict[str, Any], message: str) -> dict[str, Any]:
    try:
        normalized = validate_operation(operation)
    except (OperationValidationError, TypeError, ValueError) as exc:
        return _response("Rejected", str(exc))
    return _response("Applied", message, normalized)


def parse_prompt(prompt: str) -> dict[str, Any]:
    """Every prompt maps to one of the required three status values."""
    if not isinstance(prompt, str) or not prompt.strip():
        return _response("Needs clarification", "Enter an editing instruction.")
    text = prompt.strip()
    lower = text.lower()

    if re.search(r"\b(image|photo|picture)\b", lower) and re.search(r"\b(colori[sz]e|restore colors?)\b", lower):
        return _response("Rejected", "This application edits video files; image colorization is not supported.")

    if re.search(r"\b(reorder|swap segments)\b", lower):
        ranges = _ranges(text)
        if len(ranges) < 2:
            return _response("Needs clarification", "Specify at least two source-time ranges in output order, e.g. reorder 5 to 10, then 0 to 5 seconds.")
        return _validated(
            {"operation_type": "reorder", "parameters": {"segments": [{"start": start, "end": end} for start, end in ranges]}},
            "Reorder instruction was added using original source timestamps.",
        )

    interval = _one_range(text)
    if re.search(r"\b(cut|remove|delete|trim out)\b", lower):
        if not interval:
            return _response("Needs clarification", "Specify a start and end time for the section to cut.")
        start, end = interval
        return _validated({"operation_type": "cut", "parameters": {"start": start, "end": end}}, f"Cut from {start:g}s to {end:g}s was added to the timeline.")

    if re.search(r"\b(bleep|beep)\b", lower):
        if not interval:
            return _response("Needs clarification", "Specify the start and end time for the bleep.")
        start, end = interval
        return _validated({"operation_type": "bleep", "parameters": {"start": start, "end": end, "frequency": 1000}}, f"Bleep from {start:g}s to {end:g}s was added to the timeline.")

    if re.search(r"\b(mute|silence)\b", lower):
        if not interval:
            return _response("Needs clarification", "Specify the start and end time to mute.")
        start, end = interval
        return _validated({"operation_type": "mute", "parameters": {"start": start, "end": end}}, f"Mute from {start:g}s to {end:g}s was added to the timeline.")

    if re.search(r"\b(caption|subtitle|add text|show text)\b", lower):
        quoted = re.search(r"['\"]([^'\"]{1,300})['\"]", text)
        if not quoted:
            return _response("Needs clarification", "Put caption text in quotes, e.g. add caption 'Hello' at 2 seconds.")
        if interval:
            start, end = interval
        else:
            point = _point_after_at(text)
            if point is None:
                return _response("Needs clarification", "Specify when the caption should appear, using a timestamp or time range.")
            start, end = point, point + 3.0
        return _validated({"operation_type": "caption", "parameters": {"start": start, "end": end, "text": quoted.group(1).strip()}}, f"Caption anchored to original source time {start:g}s–{end:g}s.")

    effect = None
    value = None
    if any(phrase in lower for phrase in ("black and white", "black-and-white", "grayscale", "greyscale")):
        effect = "grayscale"
    elif "brightness" in lower:
        effect = "brightness"
        value = -0.15 if any(word in lower for word in ("decrease", "lower", "reduce", "less")) else 0.15
    elif "contrast" in lower:
        effect = "contrast"
        value = 0.8 if any(word in lower for word in ("decrease", "lower", "reduce", "less")) else 1.2
    elif "saturation" in lower:
        effect = "saturation"
        value = 0.8 if any(word in lower for word in ("decrease", "lower", "reduce", "less")) else 1.2
    if effect:
        params: dict[str, Any] = {"name": effect}
        if interval:
            params.update({"start": interval[0], "end": interval[1]})
        else:
            params["whole_source"] = True
        if value is not None:
            params["value"] = value
        return _validated({"operation_type": "effect", "parameters": params}, f"{effect.replace('_', ' ')} effect was added to the timeline.")

    if re.search(r"\b(speed|faster|slower)\b", lower):
        factor_match = re.search(r"\b(\d+(?:\.\d+)?)\s*x\b", lower)
        if factor_match:
            factor = float(factor_match.group(1))
            if "slower" in lower and factor > 1:
                factor = 1.0 / factor
        else:
            factor = 2.0 if "faster" in lower else 0.5
        params = {"factor": factor}
        if interval:
            params.update({"start": interval[0], "end": interval[1]})
        else:
            params["whole_source"] = True
        return _validated({"operation_type": "speed", "parameters": params}, f"Speed factor {factor:g}x was added to the timeline.")

    return _response("Needs clarification", "I couldn't identify this edit. Try cut, mute, bleep, caption, visual effect, speed or reorder with clear values.")
