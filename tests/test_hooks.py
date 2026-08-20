from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
STOP_HOOK = ROOT / ".codex/hooks/stop_validation.py"


class StopHookTests(unittest.TestCase):
    def run_hook(self, root: Path) -> dict:
        payload = json.dumps({"cwd": str(root)})
        completed = subprocess.run(
            [sys.executable, str(STOP_HOOK)],
            input=payload,
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(completed.stdout)

    def write_config(self, root: Path, profile: str, command: Path) -> None:
        path = root / ".harness/validation.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "mode": "profile",
                    "profiles": [profile],
                    "commands": [
                        {
                            "name": "project-check",
                            "command": [str(command)],
                            "reason": "project-defined stop check",
                            "roles": ["stop"],
                        }
                    ],
                    "stopChecks": ["project-check"],
                }
            ),
            encoding="utf-8",
        )

    def test_node_and_python_profiles_use_configured_stop_command(self) -> None:
        for profile in ("node", "python"):
            with self.subTest(profile=profile), TemporaryDirectory() as temp:
                root = Path(temp)
                command = root / "check"
                command.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                command.chmod(0o755)
                self.write_config(root, profile, command)

                result = self.run_hook(root)

                self.assertEqual({"continue": True}, result)

    def test_failed_project_check_blocks_stop_and_redacts_output(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            command = root / "check"
            command.write_text(
                "#!/bin/sh\necho 'token=secret customer@example.com' >&2\nexit 1\n",
                encoding="utf-8",
            )
            command.chmod(0o755)
            self.write_config(root, "node", command)

            result = self.run_hook(root)

            self.assertEqual("block", result["decision"])
            self.assertNotIn("secret", result["reason"])
            self.assertNotIn("customer@example.com", result["reason"])

    def test_malformed_profile_blocks_stop_fail_closed(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / ".harness/validation.json"
            config.parent.mkdir()
            config.write_text("{bad", encoding="utf-8")

            result = self.run_hook(root)

            self.assertEqual("block", result["decision"])


if __name__ == "__main__":
    unittest.main()
