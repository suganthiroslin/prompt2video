"""Validation helpers for originals and operation histories."""

from pathlib import Path
from typing import Any

from core.hashing import sha256_file
from core.operations import OperationValidationError, validate_operation


def verify_original(file_path: str | Path, expected_sha256: str) -> dict[str, Any]:
    path = Path(file_path)
    if not path.is_file():
        return {"valid": False, "message": "Original file is missing.", "actual_sha256": None}
    actual = sha256_file(path)
    valid = actual == expected_sha256
    return {
        "valid": valid,
        "message": "Original is unchanged." if valid else "Original hash has changed.",
        "expected_sha256": expected_sha256,
        "actual_sha256": actual,
    }


def validate_operations(operations: list[dict[str, Any]]) -> dict[str, Any]:
    errors = []
    for index, operation in enumerate(operations):
        try:
            validate_operation(operation)
        except OperationValidationError as exc:
            errors.append({"index": index, "message": str(exc)})
    return {"valid": not errors, "errors": errors}
