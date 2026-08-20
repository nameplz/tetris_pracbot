from __future__ import annotations

import json
import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.phase_worktree import (  # noqa: E402
    MAX_STUCK_RETRIES,
    STATUS_UPDATE_INTERVAL_SECONDS,
    STUCK_AFTER_SECONDS,
    PhaseWorktreeError,
    ensure_phase_completed,
    is_stuck,
    next_stuck_state,
    validate_phase_name,
    write_heartbeat,
)


class PhaseWorktreeTests(unittest.TestCase):
    def test_phase_name_rejects_path_traversal(self) -> None:
        with self.assertRaises(PhaseWorktreeError):
            validate_phase_name("../bad")

    def test_incomplete_phase_blocks_open_pr(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            phase_dir = root / "phases/0-mvp"
            phase_dir.mkdir(parents=True)
            (phase_dir / "index.json").write_text(
                json.dumps(
                    {
                        "project": "demo",
                        "phase": "0-mvp",
                        "steps": [{"step": 0, "name": "setup", "status": "pending"}],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(PhaseWorktreeError):
                ensure_phase_completed(root, "0-mvp")

    def test_heartbeat_writes_ignored_runtime_state_shape(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)

            path = write_heartbeat(
                root=root,
                phase="0-mvp",
                step=2,
                attempt=3,
                status="running",
                message="working",
            )

            self.assertEqual(root / ".harness/runtime/0-mvp/step2-attempt3.json", path)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual("0-mvp", data["phase"])
            self.assertEqual(2, data["step"])
            self.assertEqual(3, data["attempt"])
            self.assertEqual("running", data["status"])

    def test_heartbeat_records_start_elapsed_progress_and_separate_retries(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            started = datetime(2026, 1, 1, tzinfo=UTC)
            updated = started + timedelta(seconds=540)

            path = write_heartbeat(
                root=root,
                phase="0-mvp",
                step=2,
                attempt=3,
                status="running",
                message="integration tests 작성 중",
                started_at=started,
                now=updated,
                stuck_retry=1,
                pipeline_attempt=3,
            )

            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(started.isoformat(), data["started_at"])
            self.assertEqual(updated.isoformat(), data["updated_at"])
            self.assertEqual(540, data["elapsed_seconds"])
            self.assertEqual("integration tests 작성 중", data["progress"])
            self.assertEqual(STATUS_UPDATE_INTERVAL_SECONDS, data["status_update_interval_seconds"])
            self.assertEqual(STUCK_AFTER_SECONDS, data["stuck_after_seconds"])
            self.assertEqual(1, data["stuck_retry"])
            self.assertEqual(3, data["pipeline_attempt"])
            self.assertEqual(MAX_STUCK_RETRIES, data["max_stuck_retries"])

    def test_stuck_uses_attempt_start_not_last_heartbeat(self) -> None:
        started = datetime(2026, 1, 1, tzinfo=UTC)

        self.assertFalse(
            is_stuck(
                started_at=started,
                now=started + timedelta(seconds=STUCK_AFTER_SECONDS - 1),
                status="running",
            )
        )
        self.assertTrue(
            is_stuck(
                started_at=started,
                now=started + timedelta(seconds=STUCK_AFTER_SECONDS),
                status="running",
            )
        )
        self.assertTrue(
            is_stuck(
                started_at=started,
                now=started + timedelta(seconds=STUCK_AFTER_SECONDS + 1),
                status="running",
            )
        )
        self.assertFalse(
            is_stuck(
                started_at=started,
                now=started + timedelta(seconds=STUCK_AFTER_SECONDS + 1),
                status="completed",
            )
        )

    def test_stuck_state_retries_then_errors_without_touching_pipeline_retry(self) -> None:
        self.assertEqual(("stuck", 1), next_stuck_state(0, max_stuck_retries=3))
        self.assertEqual(("stuck", 3), next_stuck_state(2, max_stuck_retries=3))
        self.assertEqual(("error", 3), next_stuck_state(3, max_stuck_retries=3))


if __name__ == "__main__":
    unittest.main()
