#!/usr/bin/env python3

from __future__ import annotations

import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

SUPERVISOR = Path(__file__).with_name("strict-bright-agent-supervisor.py")


class StrictBrightAgentSupervisorTest(unittest.TestCase):
    def invoke(self, code: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SUPERVISOR), sys.executable, "-c", code, *args],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )

    def test_known_fallback_markers_fail(self) -> None:
        for marker in (
            "falling back to function harness mode",
            "falling back to function harness",
        ):
            with self.subTest(marker=marker):
                result = self.invoke(
                    "import sys, time; print(sys.argv[1], flush=True); time.sleep(30)",
                    marker,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(marker, result.stdout)
                self.assertIn("Function harness blocked", result.stderr)

    def test_marker_kills_the_child_process_group(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sentinel = Path(directory, "harness-continued")
            child_code = (
                "import pathlib, sys, time; time.sleep(1); "
                "pathlib.Path(sys.argv[1]).write_text('alive')"
            )
            parent_code = (
                "import subprocess, sys, time; "
                "subprocess.Popen([sys.executable, '-c', sys.argv[2], sys.argv[1]]); "
                "print('falling back to function harness mode', flush=True); "
                "time.sleep(30)"
            )
            result = self.invoke(parent_code, str(sentinel), child_code)
            time.sleep(1.1)

            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(sentinel.exists())

    def test_normal_command_preserves_output_and_exit_code(self) -> None:
        result = self.invoke(
            "import sys; print('normal stdout'); "
            "print('normal stderr', file=sys.stderr); sys.exit(23)"
        )

        self.assertEqual(result.returncode, 23)
        self.assertIn("normal stdout", result.stdout)
        self.assertIn("normal stderr", result.stderr)


if __name__ == "__main__":
    unittest.main()
