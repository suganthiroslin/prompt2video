"""In-memory session store joining uploads, timeline state, and render outputs."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config import Config
from core.hashing import sha256_file
from core.models import EditSession, OriginalMedia
from services.render_service import probe_media
from services.timeline_service import TimelineService


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SessionRecord:
    session: EditSession
    timeline_service: TimelineService
    original_path: Optional[str] = None
    original_sha256: Optional[str] = None
    original_filename: Optional[str] = None
    rendered_path: Optional[str] = None
    rendered_timeline_hash: Optional[str] = None
    render_status: str = "not_rendered"
    render_error: Optional[str] = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    @property
    def session_id(self) -> str:
        return str(self.session.session_id)

    def touch(self):
        self.updated_at = _now()

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "has_original": bool(self.original_path),
            "original_filename": self.original_filename,
            "original_sha256": self.original_sha256,
            "has_rendered_output": self.render_status == "rendered",
            "render_status": self.render_status,
            "rendered_timeline_hash": self.rendered_timeline_hash,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "time_policy": self.session.time_policy,
        }


class SessionStore:
    """In-memory registry. Uploaded/renders persist on disk; session IDs do not."""
    def __init__(self):
        Config.ensure_directories()
        self.sessions: dict[str, SessionRecord] = {}

    def create_session(self) -> EditSession:
        session = EditSession()
        record = SessionRecord(session=session, timeline_service=TimelineService())
        self.sessions[str(session.session_id)] = record
        return session

    def get_record(self, session_id: str) -> Optional[SessionRecord]:
        return self.sessions.get(str(session_id))

    def get_session(self, session_id: str) -> Optional[EditSession]:
        rec = self.get_record(session_id)
        return rec.session if rec else None

    def get_timeline_service(self, session_id: str) -> Optional[TimelineService]:
        rec = self.get_record(session_id)
        return rec.timeline_service if rec else None

    def session_exists(self, session_id: str) -> bool:
        return str(session_id) in self.sessions

    def list_sessions(self) -> list[dict]:
        return [record.to_dict() for record in self.sessions.values()]

    def register_original(self, session_id: str, file_path: str | Path, original_filename: str | None = None) -> dict:
        rec = self._require(session_id)
        path = Path(file_path).resolve()
        if rec.original_path:
            raise ValueError("This session already has an original video. Create a new session to edit a different source.")
        if not path.is_file():
            raise FileNotFoundError(f"Original video does not exist: {path}")
        if not Config.is_allowed_video_filename(path.name):
            raise ValueError("Unsupported video extension. Allowed formats: MP4, MOV, AVI, MKV, WebM.")
        metadata = probe_media(path)
        source_hash = sha256_file(path)
        original = OriginalMedia(
            file_path=str(path), sha256=source_hash, duration=float(metadata["duration"]),
            fps=float(metadata["fps"]), width=int(metadata["width"]),
            height=int(metadata["height"]), has_audio=bool(metadata["has_audio"]),
        )
        rec.session.original = original
        rec.original_path = str(path)
        rec.original_sha256 = source_hash
        rec.original_filename = original_filename or path.name
        rec.rendered_path = None
        rec.rendered_timeline_hash = None
        rec.render_status = "not_rendered"
        rec.render_error = None
        rec.touch()
        return {"session_id": rec.session_id, "original": original.to_dict(), "original_unchanged": True}

    def verify_original(self, session_id: str) -> dict:
        rec = self._require(session_id)
        if not rec.original_path or not rec.original_sha256:
            return {"valid": False, "message": "No original video is registered.", "actual_sha256": None}
        path = Path(rec.original_path)
        if not path.is_file():
            return {"valid": False, "message": "Original video file is missing.", "expected_sha256": rec.original_sha256, "actual_sha256": None}
        actual = sha256_file(path)
        return {"valid": actual == rec.original_sha256, "message": "Original is unchanged." if actual == rec.original_sha256 else "Original hash changed.", "expected_sha256": rec.original_sha256, "actual_sha256": actual}

    def mark_rendering(self, session_id: str) -> None:
        rec = self._require(session_id)
        if not rec.original_path:
            raise ValueError("Upload an original video before rendering.")
        verify = self.verify_original(session_id)
        if not verify["valid"]:
            raise ValueError("Original video is missing or has changed; rendering was stopped.")
        rec.render_status, rec.render_error = "rendering", None
        rec.touch()

    def set_rendered_output(self, session_id: str, rendered_path: str | Path, timeline_hash: str) -> dict:
        rec = self._require(session_id)
        if not rec.original_path:
            raise ValueError("No original video is registered.")
        output = Path(rendered_path).resolve()
        source = Path(rec.original_path).resolve()
        if not output.is_file():
            raise FileNotFoundError(f"Rendered output not found: {output}")
        if output == source:
            raise ValueError("Rendered output must not overwrite the original.")
        if not timeline_hash:
            raise ValueError("Timeline hash is required to register rendered output.")
        verify = self.verify_original(session_id)
        if not verify["valid"]:
            raise ValueError("Original video verification failed after rendering.")
        rec.rendered_path = str(output)
        rec.rendered_timeline_hash = timeline_hash
        rec.render_status, rec.render_error = "rendered", None
        rec.touch()
        return {"session_id": rec.session_id, "render_status": rec.render_status, "rendered_filename": output.name, "rendered_path": str(output), "timeline_hash": timeline_hash, "original_unchanged": True}

    def invalidate_render(self, session_id: str) -> None:
        rec = self._require(session_id)
        if rec.rendered_path:
            rec.render_status = "out_of_date"
        else:
            rec.render_status = "not_rendered"
        rec.rendered_timeline_hash = None
        rec.touch()

    def mark_render_failed(self, session_id: str, message: str) -> None:
        rec = self._require(session_id)
        rec.render_status = "failed"
        rec.render_error = str(message)
        rec.touch()

    def get_rendered_path(self, session_id: str, expected_timeline_hash: str | None = None) -> Optional[str]:
        rec = self.get_record(session_id)
        if not rec or rec.render_status != "rendered" or not rec.rendered_path:
            return None
        if expected_timeline_hash and rec.rendered_timeline_hash != expected_timeline_hash:
            return None
        if not Path(rec.rendered_path).is_file():
            return None
        check = self.verify_original(session_id)
        if not check["valid"] or Path(rec.rendered_path).resolve() == Path(rec.original_path).resolve():
            return None
        return str(Path(rec.rendered_path).resolve())

    def delete_session(self, session_id: str) -> bool:
        return self.sessions.pop(str(session_id), None) is not None

    def _require(self, session_id: str) -> SessionRecord:
        record = self.get_record(session_id)
        if record is None:
            raise KeyError(f"Unknown editing session: {session_id}")
        return record
