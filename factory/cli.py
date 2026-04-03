from __future__ import annotations

import argparse

from .codex import build_command, run_codex_phase, run_verification
from .config import load_config
from .state import append_run, load_state, summarize_state


PHASE_CHOICES = ["bootstrap", "deliver", "optimize", "autofix"]


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Codex factory starter CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status", help="Show config and recent run state")

    show_parser = subparsers.add_parser(
        "show-command", help="Print the Codex command used for automation"
    )
    show_parser.add_argument("phase", choices=PHASE_CHOICES)

    run_parser = subparsers.add_parser("run-phase", help="Run one Codex phase")
    run_parser.add_argument("phase", choices=PHASE_CHOICES)
    run_parser.add_argument("--dry-run", action="store_true", help="Do not call Codex")
    run_parser.add_argument(
        "--skip-verify", action="store_true", help="Skip verification after the phase"
    )

    loop_parser = subparsers.add_parser("run-loop", help="Run multiple phases in order")
    loop_parser.add_argument(
        "--phases",
        nargs="+",
        default=["deliver", "optimize"],
        choices=PHASE_CHOICES,
    )
    loop_parser.add_argument("--dry-run", action="store_true")
    loop_parser.add_argument("--skip-verify", action="store_true")

    subparsers.add_parser("verify", help="Run verification commands from factory.toml")
    return parser


def print_status() -> int:
    config = load_config()
    state = load_state(config.state_file)
    print(f"project_name: {config.project_name}")
    print(f"codex_command: {config.codex_command}")
    print(f"codex_args: {' '.join(config.codex_args)}")
    print("phases:")
    for name, phase in config.phases.items():
        print(f"  - {name}: {phase.description}")
    print("verify_commands:")
    for command in config.verify_commands:
        print(f"  - {command}")
    print("recent_runs:")
    print(summarize_state(state))
    return 0


def print_command(phase_name: str) -> int:
    config = load_config()
    phase = config.phases[phase_name]
    command = build_command(config)
    print("command:")
    print(" ".join(command))
    print(f"prompt_file: {phase.prompt_file}")
    return 0


def run_phase(phase_name: str, *, dry_run: bool, skip_verify: bool) -> int:
    config = load_config()
    phase = config.phases[phase_name]
    result = run_codex_phase(config, phase, dry_run=dry_run)

    status = "success" if result.ok else "failed"
    if dry_run:
        status = "dry-run"

    append_run(
        config.state_file,
        phase=phase.name,
        status=status,
        prompt_file=str(result.prompt_path),
        stdout_file=str(result.stdout_path),
        stderr_file=str(result.stderr_path),
        max_entries=config.max_run_history,
    )

    print(f"phase: {phase.name}")
    print(f"status: {status}")
    print(f"prompt_log: {result.prompt_path}")
    print(f"stdout_log: {result.stdout_path}")
    print(f"stderr_log: {result.stderr_path}")
    print(f"command: {' '.join(result.command)}")

    if not result.ok:
        return result.returncode

    if skip_verify or not phase.run_verification:
        return 0

    return verify()


def run_loop(phases: list[str], *, dry_run: bool, skip_verify: bool) -> int:
    for phase in phases:
        code = run_phase(phase, dry_run=dry_run, skip_verify=skip_verify)
        if code != 0:
            return code
    return 0


def verify() -> int:
    config = load_config()
    if not config.verify_commands:
        print("No verification commands configured.")
        return 0

    config.log_dir.mkdir(parents=True, exist_ok=True)
    verify_log = config.log_dir.parent / "verify.log"
    exit_code, results = run_verification(config.verify_commands)

    lines: list[str] = []
    for command, code in results:
        line = f"[{code}] {command}"
        print(line)
        lines.append(line)

    verify_log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return exit_code


def main(argv: list[str] | None = None) -> int:
    parser = make_parser()
    args = parser.parse_args(argv)

    if args.command == "status":
        return print_status()
    if args.command == "show-command":
        return print_command(args.phase)
    if args.command == "run-phase":
        return run_phase(args.phase, dry_run=args.dry_run, skip_verify=args.skip_verify)
    if args.command == "run-loop":
        return run_loop(args.phases, dry_run=args.dry_run, skip_verify=args.skip_verify)
    if args.command == "verify":
        return verify()

    parser.error("Unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
