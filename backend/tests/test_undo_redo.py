from services.timeline_service import TimelineService


def test_one_instruction_is_one_undo_and_redo():
    service = TimelineService()
    first = service.process_prompt("Cut the video from 1 to 2 seconds")
    second = service.process_prompt("Mute the audio from 4 to 5 seconds")
    assert first["status"] == second["status"] == "Applied"
    assert len(service.get_timeline()["operations"]) == 2
    assert service.undo()["status"] == "Applied"
    assert len(service.get_timeline()["operations"]) == 1
    assert service.redo()["status"] == "Applied"
    assert len(service.get_timeline()["operations"]) == 2


def test_new_edit_clears_redo_history():
    service = TimelineService()
    service.process_prompt("Cut the video from 1 to 2 seconds")
    service.process_prompt("Mute the audio from 4 to 5 seconds")
    service.undo()
    assert service.history_service.can_redo
    service.process_prompt("Bleep from 6 to 7 seconds")
    assert not service.history_service.can_redo
    assert len(service.get_timeline()["operations"]) == 2


def test_restore_specific_earlier_version():
    service = TimelineService()
    service.process_prompt("Cut the video from 1 to 2 seconds")  # version 1
    service.process_prompt("Mute the audio from 4 to 5 seconds")  # version 2
    result = service.restore(1)
    assert result["status"] == "Applied"
    assert result["restored_version"] == 1
    ops = service.get_timeline()["operations"]
    assert len(ops) == 1 and ops[0]["operation_type"] == "cut"
    assert service.history_service.can_undo
