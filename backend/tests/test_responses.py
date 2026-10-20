import pytest
from services.prompt_service import parse_prompt


@pytest.mark.parametrize("prompt", [
    "Cut the video from 2 to 5 seconds",
    "Mute the audio from 5 to 7 seconds",
    "Bleep from 2 to 3 seconds",
    "Add caption 'Hello' from 1 to 3 seconds",
    "Apply a black-and-white effect from 0 to 2 seconds",
    "Make the video 2x faster",
    "Reorder 3 to 5 seconds, then 0 to 3 seconds",
])
def test_supported_prompts_return_applied(prompt):
    assert parse_prompt(prompt)["status"] == "Applied"


def test_unclear_prompt_needs_clarification():
    assert parse_prompt("Make it better")["status"] == "Needs clarification"


def test_image_colorization_is_rejected_as_out_of_scope():
    assert parse_prompt("Colorize this black-and-white image")["status"] == "Rejected"


def test_blank_prompt_needs_clarification():
    assert parse_prompt("  ")["status"] == "Needs clarification"


def test_timestamp_outside_uploaded_source_is_rejected_without_edit():
    from services.timeline_service import TimelineService
    service = TimelineService()
    result = service.process_prompt("Cut the video from 2 to 9 seconds", source_duration=6.0)
    assert result["status"] == "Rejected"
    assert service.get_timeline()["operations"] == []


def test_timeline_service_also_returns_three_way_statuses():
    from services.timeline_service import TimelineService
    service = TimelineService()
    unclear = service.process_prompt("Make it better")
    assert unclear["status"] == "Needs clarification"
    unsupported = service.process_prompt("Colorize this black-and-white image")
    assert unsupported["status"] == "Rejected"
