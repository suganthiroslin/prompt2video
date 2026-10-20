# 8-minute assessment demo checklist

Use a short 6–10 second MP4 with visible scene changes and audio. Pre-run tests so the video recording is not spent waiting for dependency installation.

## Suggested recording (target: 7:45)

- **0:00–0:30 — Introduction:** show frontend, backend health and original-source-time policy.
- **0:30–1:15 — Original protection:** create session, upload original, show its SHA-256, apply one edit, verify the original hash again.
- **1:15–2:25 — Edit prompts:** demonstrate cut, mute/bleep, caption, visual effect, speed and reorder. Show the structured timeline operations.
- **2:25–3:00 — Three-way status:** show one applied prompt, one unclear prompt (`Make it better`) and one rejected out-of-scope image-colorization request.
- **3:00–3:35 — Determinism:** run `python session_runner.py --script demo_session.json --runs 3`; show matching hashes.
- **3:35–4:25 — History:** undo, redo, create a new edit after undo, and restore an earlier timeline version.
- **4:25–5:50 — Render proof:** click Render, show the actual rendered MP4, play it, show duration/A-V duration comparison and original hash verification.
- **5:50–6:20 — Time policy:** show that timestamps remain on original source time after cuts/reorder.
- **6:20–7:45 — Integration and evidence:** show output file in `backend/media/renders/`, verification JSON, saved history JSON and passing pytest summary.

Do not claim an untested feature is complete. The rule-based parser accepts explicit timestamps; it does not automatically transcribe speech into word-level timestamps. Review the rendered video and generated `*.verification.json` report before recording.

## Demo prompts

```text
Cut the video from 2 to 4 seconds
Mute the audio from 5 to 6 seconds
Bleep from 3 to 4 seconds
Add caption 'Assessment demo' from 1 to 3 seconds
Apply a black-and-white effect from 3 to 5 seconds
Make the video 2x faster
Reorder 3 to 6 seconds, then 0 to 3 seconds
Make it better
Colorize this black-and-white image
```

Each prompt should be tested with a source video long enough to include the requested timestamps. For the render accuracy demo, test both an uncomplicated cut and a mixed-operation timeline, and show the machine-generated verification report.
