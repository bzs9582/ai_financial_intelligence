from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


@dataclass(slots=True)
class PhaseConfig:
    name: str
    prompt_file: Path
    description: str
    run_verification: bool


@dataclass(slots=True)
class FactoryConfig:
    project_name: str
    codex_command: str
    codex_args: list[str]
    verify_commands: list[str]
    state_file: Path
    log_dir: Path
    max_run_history: int
    phases: dict[str, PhaseConfig]


def load_config(path: Path | None = None) -> FactoryConfig:
    root = repo_root()
    config_path = path or root / "factory.toml"
    raw = tomllib.loads(config_path.read_text(encoding="utf-8"))

    phases: dict[str, PhaseConfig] = {}
    for name, value in raw["phases"].items():
        phases[name] = PhaseConfig(
            name=name,
            prompt_file=root / value["prompt_file"],
            description=value["description"],
            run_verification=bool(value.get("run_verification", True)),
        )

    return FactoryConfig(
        project_name=raw["project_name"],
        codex_command=raw["codex_command"],
        codex_args=list(raw.get("codex_args", [])),
        verify_commands=list(raw.get("verify_commands", [])),
        state_file=root / raw.get("state_file", ".factory/state.json"),
        log_dir=root / raw.get("log_dir", ".factory/logs"),
        max_run_history=int(raw.get("max_run_history", 40)),
        phases=phases,
    )
