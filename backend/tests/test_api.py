import io
import pytest
pytest.importorskip("flask")
from app import app, store


def test_health_and_session_api():
    app.testing = True
    client = app.test_client()
    assert client.get("/api/health").status_code == 200
    created = client.post("/api/session", json={})
    assert created.status_code == 201
    session_id = created.get_json()["session_id"]
    result = client.post("/api/prompt", json={"session_id": session_id, "prompt": "Cut the video from 1 to 2 seconds"})
    assert result.status_code == 200
    assert result.get_json()["status"] == "Applied"
    timeline = client.get(f"/api/timeline/{session_id}").get_json()
    assert len(timeline["operations"]) == 1


def test_prompt_requires_session():
    app.testing = True
    client = app.test_client()
    response = client.post("/api/prompt", json={"prompt": "Cut from 1 to 2 seconds"})
    assert response.get_json()["status"] == "Needs clarification"


def test_upload_render_preview_download_end_to_end(sample_video):
    app.testing = True
    client = app.test_client()
    created = client.post("/api/session", json={}).get_json()
    session_id = created["session_id"]
    with open(sample_video, "rb") as handle:
        upload = client.post(
            f"/api/upload/{session_id}",
            data={"file": (io.BytesIO(handle.read()), "sample.mp4")},
            content_type="multipart/form-data",
        )
    assert upload.status_code == 201, upload.get_json()
    prompt = client.post("/api/prompt", json={"session_id": session_id, "prompt": "Cut the video from 2 to 4 seconds"})
    assert prompt.get_json()["status"] == "Applied"
    rendered = client.post(f"/api/render/{session_id}", json={})
    assert rendered.status_code == 200, rendered.get_json()
    assert rendered.get_json()["verification"]["within_one_frame"] is True
    assert client.get(f"/api/preview/{session_id}").status_code == 200
    assert client.get(f"/api/download/{session_id}").status_code == 200
    assert client.get(f"/api/verify-original/{session_id}").get_json()["valid"] is True
