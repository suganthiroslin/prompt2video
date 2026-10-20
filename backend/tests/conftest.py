from pathlib import Path
import subprocess
import pytest
import imageio_ffmpeg


@pytest.fixture
def sample_video(tmp_path: Path) -> Path:
    """Create a 6-second 25-fps test clip with audio using bundled FFmpeg."""
    output = tmp_path / "sample.mp4"
    command = [
        imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=25",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
        "-t", "6", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "96k", str(output),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        pytest.skip(f"Bundled FFmpeg cannot generate the test fixture: {result.stderr[-500:]}")
    return output
