from pathlib import Path
import unittest

from factory.config import load_config, repo_root


class ConfigTests(unittest.TestCase):
    def test_loads_expected_phases(self) -> None:
        config = load_config()
        self.assertIn("bootstrap", config.phases)
        self.assertIn("deliver", config.phases)
        self.assertIn("optimize", config.phases)
        self.assertIn("autofix", config.phases)

    def test_prompt_paths_are_repo_relative(self) -> None:
        config = load_config()
        for phase in config.phases.values():
            self.assertTrue(str(phase.prompt_file).startswith(str(repo_root())))
            self.assertEqual(Path(phase.prompt_file).suffix, ".md")


if __name__ == "__main__":
    unittest.main()
