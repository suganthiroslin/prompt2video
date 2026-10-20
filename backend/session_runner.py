"""Run the same scripted prompt session N times and compare timeline hashes.

Usage from backend/: python session_runner.py --script demo_session.json --runs 3
"""
import argparse
import json
from pathlib import Path
from services.timeline_service import TimelineService


def run_once(prompts: list[str]) -> dict:
    service = TimelineService()
    step_results = []
    for prompt in prompts:
        result = service.process_prompt(prompt)
        step_results.append({"prompt": prompt, "status": result["status"], "message": result["message"]})
        if result["status"] != "Applied":
            raise RuntimeError(f"Script prompt did not apply: {prompt!r}: {result['message']}")
    timeline = service.get_timeline()
    return {"steps": step_results, "timeline_hash": timeline["timeline_hash"], "timeline": timeline}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--script", default="demo_session.json", help="JSON file containing a list under 'prompts'")
    parser.add_argument("--runs", type=int, default=3, help="Number of identical runs (default 3)")
    args = parser.parse_args()
    if args.runs < 2:
        parser.error("Use at least 2 runs to compare determinism.")
    script_path = Path(args.script)
    if not script_path.is_file():
        parser.error(f"Script file not found: {script_path}")
    data = json.loads(script_path.read_text(encoding="utf-8"))
    prompts = data.get("prompts") if isinstance(data, dict) else None
    if not isinstance(prompts, list) or not prompts or not all(isinstance(p, str) for p in prompts):
        parser.error("Script JSON must contain a non-empty 'prompts' array of strings.")
    results = [run_once(prompts) for _ in range(args.runs)]
    hashes = [item["timeline_hash"] for item in results]
    print(json.dumps({"runs": args.runs, "hashes": hashes, "all_hashes_match": len(set(hashes)) == 1, "results": results}, indent=2))
    return 0 if len(set(hashes)) == 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
