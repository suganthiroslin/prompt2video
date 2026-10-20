# Prompt2Video — Prompt-Based Video Editing

A local Flask + HTML/CSS/JavaScript prototype for source-time-anchored video edits, timeline history, FFmpeg rendering, output download and basic render verification.

## Project structure

```text
prompt2video/
├── README.md
├── frontend/
│   ├── index.html
│   ├── studio.html
│   ├── vercel.json
│   └── static/
│       ├── style.css
│       └── script.js
└── backend/
    ├── app.py
    ├── config.py
    ├── requirements.txt
    ├── render.yaml
    ├── session_runner.py
    ├── demo_session.json
    ├── core/
    ├── services/
    ├── storage/
    ├── tests/
    └── media/{uploads,renders,fixtures,history}/
```

## Run locally on Windows

Use Python 3.12 (recommended for a reproducible environment). In Anaconda Prompt, create a clean environment and install dependencies from the extracted project root:

```cmd
conda create -n prompt2video python=3.12 -y
conda activate prompt2video
python -m pip install --upgrade pip
python -m pip install -r backend\requirements.txt
cd backend
python app.py
```

Keep the backend window open. In a second Anaconda Prompt, run the frontend static server:

```cmd
conda activate prompt2video
cd D:\path\to\prompt2video\frontend
python -m http.server 8000
```

Open `http://127.0.0.1:8000` or `http://127.0.0.1:8000/studio.html`.

## Basic use

1. Click **Create editing session**.
2. Choose a video file and click **Upload original to backend**.
3. Submit one supported prompt at a time. The supported rule-based examples include:
   - `Cut the video from 2 to 5 seconds`
   - `Mute the audio from 5 to 7 seconds`
   - `Bleep from 3 to 4 seconds`
   - `Add caption 'Hello world' from 1 to 4 seconds`
   - `Apply a black-and-white effect from 3 to 6 seconds`
   - `Make the video 2x faster`
   - `Reorder 5 to 8 seconds, then 0 to 5 seconds`
4. Click **Render video**. If rendering and checks succeed, preview and download the separate MP4. A `.verification.json` file is saved next to the rendered file.
5. The **Verify original** control recomputes the source SHA-256 hash.

All timestamps use `original_source_time`: they refer to the untouched source's timeline after prior cuts, speed changes or reordering.

## Tests and determinism runner

From `backend/` after dependencies are installed:

```cmd
python -m pytest -v
python session_runner.py --script demo_session.json --runs 3
```

The runner performs the same prompt script in fresh timeline services and prints hashes for comparison. Rendering tests generate a six-second synthetic clip using the bundled FFmpeg binary.

## What the current implementation verifies

- The upload is stored separately from the render output; the source SHA-256 is checked before and after rendering.
- Supported edits are represented as structured operations with source-time ranges.
- Cut, mute, bleep, caption, grayscale/brightness/contrast/saturation, speed changes and reordering have FFmpeg rendering paths.
- Timeline hashes exclude generated operation IDs/timestamps and are suitable for comparing deterministic sessions.
- History supports undo, redo, redo-branch clearing, and restore by timeline version.
- Render verification measures video duration with OpenCV and decoded audio duration with FFmpeg/WAV, comparing the results against a one-video-frame tolerance. Every output gets a JSON verification report.

## Important limits to verify before assessment submission

This is a local prototype, not a claim that an evaluator's full integration standard has already been met. The parser is deterministic rule-based code, not a general AI model. It accepts timestamped edits; it does **not** automatically transcribe speech to word-level timestamps. If the evaluator expects speech recognition or word-identity anchoring without user-provided times, add and test an ASR/word-alignment component before claiming that part is complete. The current anchor model preserves source-time intervals across cuts/reorder; a visual/audio review on your own test footage is still necessary for content anchoring. The built-in renderer/test measures track durations; that duration check alone does not prove lip-sync for arbitrary source footage. Review the generated verification file and listen to the output. The in-memory session registry resets when the backend process restarts; persistent cross-restart sessions are not implemented.

For Render deployment, set the frontend `window.PROMPT2EDIT_API_URL` in both HTML pages to the actual HTTPS backend URL. The local `127.0.0.1` fallback only works when using the app on the same computer as the backend. A free cloud service may have temporary-disk limits and long-render timeouts; validate the chosen hosting plan before using it for large files.
