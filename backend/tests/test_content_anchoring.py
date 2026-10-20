from services.render_service import _render_segments


def test_caption_and_mute_keep_original_source_anchor_after_cut():
    operations = [
        {"operation_type": "cut", "parameters": {"start": 2, "end": 4}},
        {"operation_type": "caption", "parameters": {"start": 5, "end": 7, "text": "Keep this caption"}},
        {"operation_type": "mute", "parameters": {"start": 5, "end": 6}},
    ]
    segments = _render_segments(operations, 8)
    section_5_6 = next(s for s in segments if s["source_start"] == 5 and s["source_end"] == 6)
    section_6_7 = next(s for s in segments if s["source_start"] == 6 and s["source_end"] == 7)
    assert section_5_6["mute"] is True
    assert section_5_6["captions"][0]["parameters"]["text"] == "Keep this caption"
    assert section_6_7["mute"] is False
    assert section_6_7["captions"][0]["parameters"]["text"] == "Keep this caption"
    assert not any(s["source_start"] >= 2 and s["source_end"] <= 4 for s in segments)


def test_caption_source_time_survives_reorder():
    operations = [
        {"operation_type": "caption", "parameters": {"start": 6, "end": 7, "text": "source anchored"}},
        {"operation_type": "reorder", "parameters": {"segments": [{"start": 5, "end": 8}, {"start": 0, "end": 5}]}},
    ]
    segments = _render_segments(operations, 8)
    first = next(s for s in segments if s["source_start"] == 6)
    assert first["captions"][0]["parameters"]["text"] == "source anchored"
