from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"runs": []}
    return json.loads(path.read_text(encoding="utf-8"))


def append_run(
    path: Path,
    *,
    phase: str,
    status: str,
    prompt_file: str,
    stdout_file: str | None = None,
    stderr_file: str | None = None,
    note: str | None = None,
    max_entries: int = 40,
) -> dict[str, Any]:
    state = load_state(path)
    runs = list(state.get("runs", []))
    runs.append(
        {
            "timestamp": utc_now(),
            "phase": phase,
            "status": status,
            "prompt_file": prompt_file,
            "stdout_file": stdout_file,
            "stderr_file": stderr_file,
            "note": note,
        }
    )
    state["runs"] = runs[-max_entries:]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return state


def summarize_state(state: dict[str, Any], limit: int = 5) -> str:
    runs = list(state.get("runs", []))[-limit:]
    if not runs:
        return "No previous runs recorded."

    lines = []
    for entry in runs:
        note = f" - {entry['note']}" if entry.get("note") else ""
        lines.append(
            f"- {entry['timestamp']} | {entry['phase']} | {entry['status']}{note}"
        )
    return "\n".join(lines)
