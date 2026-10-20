import pytest
from services.time_service import get_time_policy, parse_time
from services.timeline_service import TimelineService


def test_original_source_time_policy_is_explicit():
    policy = get_time_policy()
    assert policy["time_policy"] == "original_source_time"
    assert "original" in policy["description"].lower()


@pytest.mark.parametrize("value,expected", [(5, 5.0), ("00:05", 5.0), ("01:02", 62.0), ("01:02:03", 3723.0), ("5 seconds", 5.0)])
def test_parse_time(value, expected):
    assert parse_time(value) == expected


def test_negative_timestamp_rejected():
    with pytest.raises(ValueError):
        parse_time(-1)


def test_timestamps_remain_source_time_after_cut():
    service = TimelineService()
    service.process_prompt("Cut the video from 10 to 20 seconds")
    response = service.process_prompt("Mute the audio from 30 to 32 seconds")
    assert response["status"] == "Applied"
    assert response["time_policy"]["time_policy"] == "original_source_time"
    assert response["operation"]["parameters"]["start"] == 30
