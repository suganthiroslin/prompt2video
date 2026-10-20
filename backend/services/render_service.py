"""FFmpeg rendering for source-time-anchored timeline operations.

This renderer builds source-time slices first, applies the edits active on each
slice, then concatenates the slices. That is how captions/audio edits remain
anchored to original source time through cuts and reordering.
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import uuid
import wave
from pathlib import Path
from typing import Any

import cv2
import imageio_ffmpeg

from core.hashing import sha256_file, timeline_hash
from core.operations import validate_operation
from config import Config


class RenderError(RuntimeError):
    """Raised when FFmpeg cannot make a valid output."""


def _ffmpeg() -> str:
    configured = os.environ.get("FFMPEG_BINARY")
    if configured and Path(configured).is_file():
        return configured
    system = shutil.which("ffmpeg")
    return system or imageio_ffmpeg.get_ffmpeg_exe()


def _run(command: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "Unknown FFmpeg error").strip()
        raise RenderError(message[-5000:])
    return result


def probe_media(file_path: str | Path) -> dict[str, Any]:
    """Read basic video metadata and detect whether an audio stream exists."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Video file does not exist: {path}")
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        cap.release()
        raise RenderError("The uploaded file could not be opened as a video.")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    cap.release()
    if not math.isfinite(fps) or fps <= 0 or frames <= 0 or width <= 0 or height <= 0:
        raise RenderError("Could not read valid video dimensions, frame count and frame rate.")
    duration = frames / fps
    info = subprocess.run([_ffmpeg(), "-hide_banner", "-i", str(path)], capture_output=True, text=True, timeout=20)
    media_text = (info.stderr or "") + (info.stdout or "")
    has_audio = bool(re.search(r"Stream #\S+.*Audio:", media_text, re.IGNORECASE))
    return {
        "file_path": str(path.resolve()), "duration": duration, "fps": fps,
        "frames": frames, "width": width, "height": height, "has_audio": has_audio,
    }


def _interval(params: dict[str, Any], duration: float) -> tuple[float, float]:
    if params.get("whole_source") is True or ("start" not in params and "end" not in params):
        return 0.0, duration
    start = float(params["start"])
    end = float(params["end"])
    if start >= duration or end > duration + 1e-3:
        raise RenderError(
            f"Operation range {start:g}s–{end:g}s exceeds source duration {duration:.3f}s."
        )
    return max(0.0, start), min(duration, end)


def _merge_intervals(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    result: list[list[float]] = []
    for start, end in sorted(intervals):
        if not result or start > result[-1][1] + 1e-7:
            result.append([start, end])
        else:
            result[-1][1] = max(result[-1][1], end)
    return [(a, b) for a, b in result]


def _is_cut(t: float, cut_ranges: list[tuple[float, float]]) -> bool:
    return any(start - 1e-7 <= t < end - 1e-7 for start, end in cut_ranges)


def _active(operation: dict[str, Any], midpoint: float, duration: float) -> bool:
    params = operation.get("parameters", {})
    start, end = _interval(params, duration)
    return start - 1e-7 <= midpoint < end - 1e-7


def _escape_filter_path(path: Path) -> str:
    # FFmpeg filter arguments need colons and apostrophes escaped, particularly on Windows.
    text = path.resolve().as_posix()
    for old, new in [("\\", "\\\\"), (":", "\\:"), ("'", "\\'"), (",", "\\,"), ("[", "\\["), ("]", "\\]")]:
        text = text.replace(old, new)
    return text


def _atempo_chain(factor: float) -> str:
    parts = []
    remaining = factor
    while remaining > 2.0:
        parts.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        parts.append("atempo=0.5")
        remaining /= 0.5
    parts.append(f"atempo={remaining:.6f}")
    return ",".join(parts)


def _render_segments(operations: list[dict[str, Any]], duration: float) -> list[dict[str, Any]]:
    normalized = [validate_operation(op) for op in operations]
    cuts = _merge_intervals([_interval(op["parameters"], duration) for op in normalized if op["operation_type"] == "cut"])
    reorders = [op for op in normalized if op["operation_type"] == "reorder"]
    if reorders:
        requested = [(float(x["start"]), float(x["end"])) for x in reorders[-1]["parameters"]["segments"]]
        base_segments = []
        for start, end in requested:
            if start >= duration or end > duration + 1e-3:
                raise RenderError(f"Reorder range {start:g}s–{end:g}s exceeds source duration {duration:.3f}s.")
            base_segments.append((max(0.0, start), min(duration, end)))
    else:
        base_segments = [(0.0, duration)]

    split_points = {0.0, duration}
    for op in normalized:
        if op["operation_type"] == "reorder":
            continue
        start, end = _interval(op["parameters"], duration)
        split_points.add(start)
        split_points.add(end)
    for start, end in cuts:
        split_points.add(start)
        split_points.add(end)
    points = sorted(split_points)

    output: list[dict[str, Any]] = []
    for base_start, base_end in base_segments:
        local = [base_start] + [p for p in points if base_start + 1e-7 < p < base_end - 1e-7] + [base_end]
        for start, end in zip(local, local[1:]):
            if end - start < 1e-6:
                continue
            midpoint = (start + end) / 2
            if _is_cut(midpoint, cuts):
                continue
            active = [op for op in normalized if op["operation_type"] not in {"cut", "reorder"} and _active(op, midpoint, duration)]
            speeds = [op for op in active if op["operation_type"] == "speed"]
            factor = float(speeds[-1]["parameters"].get("factor", 1.0)) if speeds else 1.0
            effects = [op for op in active if op["operation_type"] == "effect"]
            captions = [op for op in active if op["operation_type"] == "caption"]
            mutes = [op for op in active if op["operation_type"] == "mute"]
            bleeps = [op for op in active if op["operation_type"] == "bleep"]
            output.append({
                "source_start": start, "source_end": end, "factor": factor,
                "effects": effects, "captions": captions,
                "mute": bool(mutes), "bleep": bleeps[-1] if bleeps else None,
                "duration": (end - start) / factor,
            })
    if not output:
        raise RenderError("The edit timeline removes the entire video; there is nothing to render.")
    return output


def _measure_video_duration(path: Path) -> tuple[float, float, int]:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        cap.release()
        raise RenderError("Rendered file cannot be opened as a video.")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    cap.release()
    if fps <= 0 or frame_count <= 0:
        raise RenderError("Could not measure rendered frame count and rate.")
    return frame_count / fps, fps, frame_count


def _measure_audio_duration(path: Path, work_dir: Path) -> float | None:
    wav_path = work_dir / f"audio_measure_{uuid.uuid4().hex}.wav"
    result = subprocess.run(
        [_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(path), "-map", "0:a:0", "-vn", "-ac", "2", "-ar", "48000", "-c:a", "pcm_s16le", str(wav_path)],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0 or not wav_path.exists():
        return None
    try:
        with wave.open(str(wav_path), "rb") as wav:
            return wav.getnframes() / float(wav.getframerate())
    finally:
        wav_path.unlink(missing_ok=True)


def render_video(original_path: str | Path, operations: list[dict[str, Any]], output_path: str | Path | None = None) -> dict[str, Any]:
    """Render the current timeline to a distinct MP4 and verify key measurements."""
    Config.ensure_directories()
    source = Path(original_path).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Original video does not exist: {source}")
    if output_path is None:
        output = Path(Config.RENDER_FOLDER) / f"render_{uuid.uuid4().hex}.mp4"
    else:
        output = Path(output_path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.resolve() == source:
        raise RenderError("Output path must be different from the original source path.")

    original_hash_before = sha256_file(source)
    media = probe_media(source)
    fps = media["fps"]
    duration = media["duration"]
    segments = _render_segments(operations, duration)
    expected_duration = sum(item["duration"] for item in segments)
    source_to_output_map = []
    output_cursor = 0.0
    for item in segments:
        next_cursor = output_cursor + float(item["duration"])
        source_to_output_map.append({
            "source_start": round(float(item["source_start"]), 6),
            "source_end": round(float(item["source_end"]), 6),
            "output_start": round(output_cursor, 6),
            "output_end": round(next_cursor, 6),
            "speed_factor": float(item["factor"]),
        })
        output_cursor = next_cursor

    caption_files: list[Path] = []
    temporary_work = Path(tempfile.mkdtemp(prefix="p2v_render_", dir=str(output.parent)))
    graph: list[str] = []
    try:
        video_labels, audio_labels = [], []
        for index, segment in enumerate(segments):
            start, end = segment["source_start"], segment["source_end"]
            factor = segment["factor"]
            vchain = f"[0:v:0]trim=start={start:.9f}:end={end:.9f},setpts=(PTS-STARTPTS)/{factor:.9f}"
            for effect in segment["effects"]:
                params = effect["parameters"]
                name = params["name"]
                if name in {"grayscale", "black_and_white"}:
                    vchain += ",hue=s=0"
                elif name == "brightness":
                    vchain += f",eq=brightness={float(params.get('value', 0.15)):.5f}"
                elif name == "contrast":
                    vchain += f",eq=contrast={float(params.get('value', 1.2)):.5f}"
                elif name == "saturation":
                    vchain += f",hue=s={float(params.get('value', 1.2)):.5f}"
            for caption in segment["captions"]:
                text_path = temporary_work / f"caption_{index}_{len(caption_files)}.txt"
                text_path.write_text(caption["parameters"]["text"], encoding="utf-8")
                caption_files.append(text_path)
                escaped = _escape_filter_path(text_path)
                vchain += f",drawtext=textfile='{escaped}':fontcolor=white:fontsize=h/18:box=1:boxcolor=black@0.60:boxborderw=12:x=(w-text_w)/2:y=h-text_h-36"
            vchain += f",format=yuv420p[v{index}]"
            graph.append(vchain)
            video_labels.append(f"[v{index}]")

            if segment["bleep"]:
                frequency = float(segment["bleep"]["parameters"].get("frequency", 1000))
                achain = f"sine=frequency={frequency:.3f}:sample_rate=48000:duration={segment['duration']:.9f},volume=0.22,apad=pad_dur=0.02,atrim=duration={segment['duration']:.9f}[a{index}]"
            elif not media["has_audio"]:
                achain = f"anullsrc=r=48000:cl=stereo,atrim=duration={segment['duration']:.9f},asetpts=PTS-STARTPTS[a{index}]"
            else:
                achain = f"[0:a:0]atrim=start={start:.9f}:end={end:.9f},asetpts=PTS-STARTPTS,{_atempo_chain(factor)}"
                if segment["mute"]:
                    achain += ",volume=0"
                achain += f",aformat=sample_rates=48000:channel_layouts=stereo,apad=pad_dur=0.02,atrim=duration={segment['duration']:.9f}[a{index}]"
            graph.append(achain)
            audio_labels.append(f"[a{index}]")

        graph.append("".join(sum(([video_labels[i], audio_labels[i]] for i in range(len(segments))), [])) + f"concat=n={len(segments)}:v=1:a=1[vconcat][outa]")
        # Frame-rate conversion happens once after concatenation. Applying fps
        # per segment would round every short segment independently and accumulate drift.
        graph.append(f"[vconcat]fps={fps:.8f},format=yuv420p[outv]")
        graph_text = ";".join(graph)
        command = [
            _ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
            "-filter_complex", graph_text,
            "-map", "[outv]", "-map", "[outa]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-pix_fmt", "yuv420p", "-r", f"{fps:.8f}",
            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
            str(output),
        ]
        _run(command, timeout=900)
        if not output.is_file() or output.stat().st_size == 0:
            raise RenderError("FFmpeg returned without creating an output video.")

        original_hash_after = sha256_file(source)
        if original_hash_after != original_hash_before:
            output.unlink(missing_ok=True)
            raise RenderError("Original file hash changed during rendering; output was rejected.")

        actual_video_duration, output_fps, frame_count = _measure_video_duration(output)
        audio_duration = _measure_audio_duration(output, temporary_work)
        frame_tolerance = 1.0 / output_fps + 1e-6
        video_duration_error = abs(actual_video_duration - expected_duration)
        av_sync_error = None if audio_duration is None else abs(actual_video_duration - audio_duration)
        if video_duration_error > frame_tolerance:
            output.unlink(missing_ok=True)
            raise RenderError(
                f"Rendered length differs from expected timeline by {video_duration_error:.4f}s; tolerance is one frame ({frame_tolerance:.4f}s)."
            )
        if av_sync_error is not None and av_sync_error > frame_tolerance:
            output.unlink(missing_ok=True)
            raise RenderError(
                f"Audio/video duration mismatch is {av_sync_error:.4f}s; tolerance is one frame ({frame_tolerance:.4f}s)."
            )

        current_hash = timeline_hash(operations)
        verification = {
            "original_sha256_before": original_hash_before,
            "original_sha256_after": original_hash_after,
            "original_unchanged": original_hash_before == original_hash_after,
            "timeline_hash": current_hash,
            "expected_timeline_duration_seconds": expected_duration,
            "rendered_video_duration_seconds": actual_video_duration,
            "video_duration_error_seconds": video_duration_error,
            "rendered_audio_duration_seconds": audio_duration,
            "audio_video_duration_difference_seconds": av_sync_error,
            "frame_rate": output_fps,
            "frame_count": frame_count,
            "one_frame_tolerance_seconds": frame_tolerance,
            "source_to_output_map": source_to_output_map,
            "within_one_frame": video_duration_error <= frame_tolerance and (av_sync_error is None or av_sync_error <= frame_tolerance),
        }
        metrics_path = output.with_suffix(".verification.json")
        metrics_path.write_text(json.dumps(verification, indent=2), encoding="utf-8")
        return {
            "status": "Applied", "message": "Video rendered and verification completed.",
            "rendered_path": str(output.resolve()), "rendered_filename": output.name,
            "timeline_hash": current_hash, "duration_seconds": actual_video_duration,
            "frame_rate": output_fps, "frame_count": frame_count,
            "verification": verification,
            "verification_report": str(metrics_path.resolve()),
        }
    except Exception:
        output.unlink(missing_ok=True)
        raise
    finally:
        shutil.rmtree(temporary_work, ignore_errors=True)


class RenderService:
    """Small class wrapper for code/tests that prefer an object interface."""
    def render(self, original_path: str | Path, operations: list[dict[str, Any]], output_path: str | Path | None = None) -> dict[str, Any]:
        return render_video(original_path, operations, output_path)
