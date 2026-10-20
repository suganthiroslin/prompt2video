from services.timeline_service import TimelineService


def run_script():
    service = TimelineService()
    service.process_prompt("Cut the video from 2 to 4 seconds")
    service.process_prompt("Mute the audio from 5 to 6 seconds")
    service.process_prompt("Add caption 'Review' from 1 to 3 seconds")
    return service.get_timeline()["timeline_hash"]


def test_same_script_has_same_timeline_hash_three_runs():
    hashes = [run_script() for _ in range(3)]
    assert hashes[0] == hashes[1] == hashes[2]
