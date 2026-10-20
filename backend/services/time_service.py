"""Timestamp parsing and explicit original-source-time policy."""
import math
import re
from typing import Any

TIME_POLICY = "original_source_time"


def parse_time(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("Boolean values are not valid timestamps.")
    if isinstance(value, (int, float)):
        seconds = float(value)
    else:
        text = re.sub(r"\s*(seconds?|secs?|sec|s)$", "", str(value).strip().lower()).strip()
        if not text:
            raise ValueError("Timestamp is empty.")
        if ":" in text:
            parts = text.split(":")
            if len(parts) not in (2, 3):
                raise ValueError(f"Invalid timestamp: {value}")
            try:
                numbers = [float(part) for part in parts]
            except ValueError:
                raise ValueError(f"Invalid timestamp: {value}") from None
            if any(part < 0 for part in numbers):
                raise ValueError("Timestamp cannot be negative.")
            if len(numbers) == 2:
                minutes, secs = numbers
                if secs >= 60:
                    raise ValueError("Seconds in MM:SS must be below 60.")
                seconds = minutes * 60 + secs
            else:
                hours, minutes, secs = numbers
                if minutes >= 60 or secs >= 60:
                    raise ValueError("Minutes and seconds in HH:MM:SS must be below 60.")
                seconds = hours * 3600 + minutes * 60 + secs
        else:
            try:
                seconds = float(text)
            except ValueError:
                raise ValueError(f"Invalid timestamp: {value}") from None
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError("Timestamp must be a finite non-negative number.")
    return round(seconds, 6)


def get_time_policy() -> dict[str, str]:
    return {
        "time_policy": TIME_POLICY,
        "name": "Original Source Time",
        "description": (
            "All timestamps refer to the untouched original video timeline. "
            "Cuts, speed changes and reordering do not change the coordinate "
            "system used by later instructions."
        ),
    }
