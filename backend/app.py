"""Flask API for the Prompt2Video assessment project."""
from __future__ import annotations
import uuid
from pathlib import Path
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename

from config import Config
from core.hashing import timeline_hash
from services.render_service import RenderError, render_video
from services.time_service import get_time_policy
from storage.session_store import SessionStore
from storage.history_store import HistoryStore

Config.ensure_directories()
app = Flask(__name__)
app.config.from_object(Config)
CORS(
    app,
    resources={
        r"/api/*": {
            "origins": "*"
        }
    },
    methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Accept"]
)
store = SessionStore()
history_store = HistoryStore()


def _save_history(session_id: str) -> None:
    record = store.get_record(session_id)
    if record:
        history_store.save(session_id, record.timeline_service.export_history())


def _error(status: str, message: str, http_status: int = 400, **extra):
    body = {"status": status, "message": message, **extra}
    return jsonify(body), http_status


def _record_or_error(session_id: str):
    record = store.get_record(session_id)
    if not record:
        return None, _error("Rejected", f"Unknown session ID: {session_id}", 404)
    return record, None


@app.get("/")
def root():
    return jsonify({"status": "success", "message": "Prompt-Based Video Editing API is running"})


@app.get("/api/health")
def health():
    return jsonify({"status": "success", "message": "Backend is healthy", "time_policy": get_time_policy()})


@app.post("/api/session")
def create_session():
    session = store.create_session()
    _save_history(str(session.session_id))
    return jsonify({
        "status": "Applied", "message": "Editing session created.",
        "session_id": str(session.session_id), "time_policy": get_time_policy(),
    }), 201


@app.get("/api/session/<session_id>")
def session_details(session_id: str):
    record, error = _record_or_error(session_id)
    if error:
        return error
    return jsonify(record.to_dict())


@app.post("/api/upload/<session_id>")
def upload_video(session_id: str):
    record, error = _record_or_error(session_id)
    if error:
        return error
    uploaded = request.files.get("file")
    if uploaded is None or not uploaded.filename:
        return _error("Needs clarification", "Select a video file in the file field named 'file'.")
    safe_name = secure_filename(uploaded.filename)
    if not Config.is_allowed_video_filename(safe_name):
        return _error("Rejected", "Supported video formats are MP4, MOV, AVI, MKV and WebM.")
    stored_name = f"{session_id}_{uuid.uuid4().hex}_{safe_name}"
    destination = Path(Config.UPLOAD_FOLDER) / stored_name
    try:
        uploaded.save(destination)
        registered = store.register_original(session_id, destination, original_filename=safe_name)
    except Exception as exc:
        destination.unlink(missing_ok=True)
        return _error("Rejected", f"Video upload/validation failed: {exc}")
    return jsonify({
        "status": "Applied", "message": "Original video uploaded and registered.",
        **registered, "time_policy": get_time_policy(),
    }), 201


@app.get("/api/verify-original/<session_id>")
def verify_original(session_id: str):
    _, error = _record_or_error(session_id)
    if error:
        return error
    result = store.verify_original(session_id)
    return jsonify({"status": "Applied" if result["valid"] else "Rejected", **result}), (200 if result["valid"] else 409)


@app.post("/api/prompt")
def apply_prompt():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _error("Needs clarification", "Send a JSON body containing prompt and session_id.")
    prompt = data.get("prompt")
    session_id = data.get("session_id")
    if not isinstance(prompt, str) or not prompt.strip():
        return _error("Needs clarification", "Enter an editing instruction.")
    if not session_id:
        return _error("Needs clarification", "Create a session before submitting a prompt.")
    record, error = _record_or_error(str(session_id))
    if error:
        return error
    source_duration = record.session.original.duration if record.session.original else None
    result = record.timeline_service.process_prompt(prompt, source_duration=source_duration)
    if result.get("status") == "Applied":
        store.invalidate_render(str(session_id))
        record.touch()
        _save_history(str(session_id))
    return jsonify({**result, "session_id": str(session_id), "time_policy": get_time_policy()}), 200


@app.get("/api/timeline/<session_id>")
def get_timeline(session_id: str):
    record, error = _record_or_error(session_id)
    if error:
        return error
    result = record.timeline_service.get_timeline()
    return jsonify({**result, "session_id": str(session_id), "source_uploaded": bool(record.original_path), "render_status": record.render_status})


@app.post("/api/undo/<session_id>")
def undo(session_id: str):
    record, error = _record_or_error(session_id)
    if error:
        return error
    result = record.timeline_service.undo()
    if result.get("status") == "Applied":
        store.invalidate_render(session_id)
        _save_history(session_id)
    return jsonify(result)


@app.post("/api/redo/<session_id>")
def redo(session_id: str):
    record, error = _record_or_error(session_id)
    if error:
        return error
    result = record.timeline_service.redo()
    if result.get("status") == "Applied":
        store.invalidate_render(session_id)
        _save_history(session_id)
    return jsonify(result)


@app.post("/api/restore/<session_id>")
def restore(session_id: str):
    record, error = _record_or_error(session_id)
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        version = int(data.get("version"))
    except (TypeError, ValueError):
        return _error("Needs clarification", "Provide the integer timeline version to restore.")
    result = record.timeline_service.restore(version)
    if result.get("status") == "Applied":
        store.invalidate_render(session_id)
        _save_history(session_id)
    return jsonify(result), (200 if result.get("status") != "Rejected" else 400)


@app.get("/api/history/<session_id>")
def get_history(session_id: str):
    record, error = _record_or_error(session_id)
    if error:
        return error
    return jsonify(record.timeline_service.export_history())


@app.post("/api/render/<session_id>")
def render_session(session_id: str):
    record, error = _record_or_error(session_id)
    if error:
        return error
    if not record.original_path:
        return _error("Needs clarification", "Upload an original video before rendering.")
    timeline = record.timeline_service.get_timeline()
    ops = timeline["operations"]
    current_hash = timeline_hash(ops)
    try:
        store.mark_rendering(session_id)
        rendered = render_video(record.original_path, ops)
        registered = store.set_rendered_output(session_id, rendered["rendered_path"], current_hash)
    except Exception as exc:
        try:
            store.mark_render_failed(session_id, str(exc))
        except Exception:
            pass
        return _error("Rejected", f"Rendering or verification failed: {exc}", 422)
    return jsonify({
        "status": "Applied", "message": "Render completed and verification passed.",
        **registered,
        "duration_seconds": rendered["duration_seconds"],
        "frame_rate": rendered["frame_rate"],
        "frame_count": rendered["frame_count"],
        "verification": rendered["verification"],
        "verification_report": Path(rendered["verification_report"]).name,
        "preview_url": f"/api/preview/{session_id}",
        "download_url": f"/api/download/{session_id}",
    })


@app.get("/api/preview/<session_id>")
def preview_render(session_id: str):
    record, error = _record_or_error(session_id)
    if error:
        return error
    current_hash = record.timeline_service.get_timeline()["timeline_hash"]
    rendered_path = store.get_rendered_path(session_id, current_hash)
    if not rendered_path:
        return _error("Needs clarification", "No current rendered output exists. Render the current timeline first.", 404)
    return send_file(rendered_path, mimetype="video/mp4", as_attachment=False, download_name=Path(rendered_path).name, conditional=True)


@app.get("/api/download/<session_id>")
def download_render(session_id: str):
    record, error = _record_or_error(session_id)
    if error:
        return error
    current_hash = record.timeline_service.get_timeline()["timeline_hash"]
    rendered_path = store.get_rendered_path(session_id, current_hash)
    if not rendered_path:
        return _error("Needs clarification", "No current rendered output exists. Render the current timeline first.", 404)
    return send_file(rendered_path, mimetype="video/mp4", as_attachment=True, download_name=Path(rendered_path).name, conditional=True)


@app.errorhandler(413)
def file_too_large(_error_value):
    return _error("Rejected", "Uploaded video exceeds the configured upload-size limit.", 413)


@app.errorhandler(404)
def not_found(_error_value):
    return _error("Rejected", "API route not found.", 404)


import os

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "5000")),
        debug=False
    )
