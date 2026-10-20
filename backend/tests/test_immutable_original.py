from core.hashing import sha256_file
from services.timeline_service import TimelineService


def test_timeline_edits_do_not_touch_original_file(tmp_path):
    source = tmp_path / "original.mp4"
    source.write_bytes(b"test original source bytes; never edit this file")
    before = sha256_file(source)
    service = TimelineService()
    service.process_prompt("Cut the video from 2 to 5 seconds")
    service.process_prompt("Mute the audio from 6 to 7 seconds")
    after = sha256_file(source)
    assert before == after
    assert source.read_bytes() == b"test original source bytes; never edit this file"
