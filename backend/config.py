"""Application paths and configuration for Prompt2Video."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
MEDIA_DIR = BASE_DIR / "media"
UPLOAD_DIR = MEDIA_DIR / "uploads"
RENDER_DIR = MEDIA_DIR / "renders"
FIXTURES_DIR = MEDIA_DIR / "fixtures"
HISTORY_DIR = MEDIA_DIR / "history"


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-before-deployment")
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_UPLOAD_BYTES", 500 * 1024 * 1024))
    BASE_DIR = str(BASE_DIR)
    MEDIA_FOLDER = str(MEDIA_DIR)
    UPLOAD_FOLDER = str(UPLOAD_DIR)
    RENDER_FOLDER = str(RENDER_DIR)
    FIXTURES_FOLDER = str(FIXTURES_DIR)
    HISTORY_FOLDER = str(HISTORY_DIR)
    ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
    OUTPUT_VIDEO_EXTENSION = ".mp4"
    JSON_SORT_KEYS = True
    SEND_FILE_MAX_AGE_DEFAULT = 0

    @classmethod
    def ensure_directories(cls):
        """Create all media folders, safe to call repeatedly."""
        for directory in (
            cls.MEDIA_FOLDER,
            cls.UPLOAD_FOLDER,
            cls.RENDER_FOLDER,
            cls.FIXTURES_FOLDER,
            cls.HISTORY_FOLDER,
        ):
            Path(directory).mkdir(parents=True, exist_ok=True)

    @staticmethod
    def is_allowed_video_filename(filename: str) -> bool:
        return bool(filename) and Path(filename).suffix.lower() in Config.ALLOWED_VIDEO_EXTENSIONS


Config.ensure_directories()
