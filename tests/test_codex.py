import unittest
import subprocess
import sys
from pathlib import Path

from factory.codex import build_command, build_prompt
from factory.config import load_config


class CodexTests(unittest.TestCase):
    def test_build_command_starts_with_codex_exec(self) -> None:
        config = load_config()
        command = build_command(config)
        self.assertGreaterEqual(len(command), 2)
        executable = Path(command[0]).name.lower()
        self.assertIn(executable, {"codex", "codex.exe"})
        self.assertEqual(command[1], "exec")

    def test_prompt_contains_runtime_context(self) -> None:
        config = load_config()
        prompt = build_prompt(config, config.phases["bootstrap"])
        self.assertIn("<runtime_context>", prompt)
        self.assertIn("project_name:", prompt)
        self.assertIn("docs/tasks.md", prompt)

    def test_cli_module_entrypoint_runs(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "factory.cli", "status"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0)
        self.assertIn("project_name:", completed.stdout)


if __name__ == "__main__":
    unittest.main()
