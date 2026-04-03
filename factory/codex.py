from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import shlex
import subprocess
from typing import Sequence

from .config import FactoryConfig, PhaseConfig, repo_root
from .state import load_state, summarize_state


@dataclass(slots=True)
class CodexRunResult:
    phase: str
    returncode: int
    prompt_path: Path
    stdout_path: Path
    stderr_path: Path
    command: list[str]

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _split_command(command: str) -> list[str]:
    return shlex.split(command, posix=False)


def build_prompt(config: FactoryConfig, phase: PhaseConfig) -> str:
    state = load_state(config.state_file)
    prompt_text = phase.prompt_file.read_text(encoding="utf-8").strip()
    runtime_context = [
        "",
        "<runtime_context>",
        f"project_name: {config.project_name}",
        f"phase: {phase.name}",
        f"repo_root: {repo_root()}",
        "last_runs:",
        summarize_state(state),
        "",
        "Important:",
        "- Read the docs before changing code.",
        "- Update docs/tasks.md when progress changes.",
        "- Run or respect verification commands from factory.toml.",
        "</runtime_context>",
        "",
    ]
    return "\n".join([prompt_text, *runtime_context])


def build_command(config: FactoryConfig) -> list[str]:
    return [*_split_command(config.codex_command), *config.codex_args]


def run_codex_phase(
    config: FactoryConfig,
    phase: PhaseConfig,
    *,
    dry_run: bool = False,
) -> CodexRunResult:
    config.log_dir.mkdir(parents=True, exist_ok=True)
    stamp = _timestamp()
    prompt_path = config.log_dir / f"{stamp}-{phase.name}.prompt.md"
    stdout_path = config.log_dir / f"{stamp}-{phase.name}.stdout.log"
    stderr_path = config.log_dir / f"{stamp}-{phase.name}.stderr.log"

    prompt = build_prompt(config, phase)
    prompt_path.write_text(prompt, encoding="utf-8")

    command = build_command(config)
    if dry_run:
        stdout_path.write_text("dry-run\n", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        return CodexRunResult(
            phase=phase.name,
            returncode=0,
            prompt_path=prompt_path,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            command=command,
        )

    completed = subprocess.run(
        command,
        input=prompt,
        cwd=repo_root(),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    stdout_path.write_text(completed.stdout or "", encoding="utf-8")
    stderr_path.write_text(completed.stderr or "", encoding="utf-8")

    return CodexRunResult(
        phase=phase.name,
        returncode=completed.returncode,
        prompt_path=prompt_path,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        command=command,
    )


def run_verification(commands: Sequence[str]) -> tuple[int, list[tuple[str, int]]]:
    results: list[tuple[str, int]] = []
    for command in commands:
        completed = subprocess.run(command, shell=True, check=False, cwd=repo_root())
        results.append((command, completed.returncode))
        if completed.returncode != 0:
            return completed.returncode, results
    return 0, results
