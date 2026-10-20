from core.hashing import sha256_file
from services.render_service import render_video


def test_cut_render_matches_expected_duration_and_preserves_source(sample_video, tmp_path):
    before_hash = sha256_file(sample_video)
    output = tmp_path / "cut_render.mp4"
    operations = [{"operation_type": "cut", "parameters": {"start": 2, "end": 4}}]
    result = render_video(sample_video, operations, output)
    assert output.is_file()
    assert output.resolve() != sample_video.resolve()
    assert sha256_file(sample_video) == before_hash
    assert result["verification"]["original_unchanged"] is True
    assert result["verification"]["within_one_frame"] is True
    assert abs(result["duration_seconds"] - 4.0) <= 1 / 25 + 0.001


def test_render_refuses_to_overwrite_original(sample_video):
    import pytest
    from services.render_service import RenderError
    with pytest.raises(RenderError):
        render_video(sample_video, [], sample_video)


def test_mixed_edits_render_within_one_frame(sample_video, tmp_path):
    operations = [
        {"operation_type": "cut", "parameters": {"start": 2, "end": 3}},
        {"operation_type": "mute", "parameters": {"start": 1, "end": 1.5}},
        {"operation_type": "bleep", "parameters": {"start": 4, "end": 4.5, "frequency": 1000}},
        {"operation_type": "caption", "parameters": {"start": 0.2, "end": 1.2, "text": "Caption test"}},
        {"operation_type": "effect", "parameters": {"start": 1.5, "end": 2.5, "name": "grayscale"}},
        {"operation_type": "speed", "parameters": {"start": 5, "end": 6, "factor": 2}},
        {"operation_type": "reorder", "parameters": {"segments": [{"start": 3, "end": 6}, {"start": 0, "end": 3}]}},
    ]
    result = render_video(sample_video, operations, tmp_path / "mixed.mp4")
    report = result["verification"]
    assert report["original_unchanged"] is True
    assert report["within_one_frame"] is True
    assert abs(report["expected_timeline_duration_seconds"] - 4.5) < 1e-6
    assert report["video_duration_error_seconds"] <= report["one_frame_tolerance_seconds"]
    assert report["audio_video_duration_difference_seconds"] <= report["one_frame_tolerance_seconds"]
