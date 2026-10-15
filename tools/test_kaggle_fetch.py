"""Offline CLI regressions for failed and successful Kaggle output downloads."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


JOB_TOOL = Path(__file__).with_name("job.py")


class KaggleFetchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.jobdir = self.root / "job"
        self.raw = self.jobdir / "result" / "raw"
        self.raw.mkdir(parents=True)
        self.summary = self.jobdir / "result" / "summary.json"
        self.cli = self.root / "fake_kaggle.py"
        self.cli.write_text(
            "import os, pathlib, sys\n"
            "exit_code = int(os.environ['FETCH_TEST_EXIT'])\n"
            "if exit_code:\n"
            "    print('download failed', file=sys.stderr)\n"
            "    sys.exit(exit_code)\n"
            "output = pathlib.Path(sys.argv[sys.argv.index('-p') + 1])\n"
            "output.mkdir(parents=True, exist_ok=True)\n"
            "(output / 'summary.json').write_text(os.environ['FETCH_TEST_SUMMARY'])\n",
            encoding="utf-8",
        )

    def fetch(self, exit_code, summary=None):
        env = dict(os.environ)
        env["KAGGLE_CLI"] = f"{sys.executable} {self.cli}"
        env["FETCH_TEST_EXIT"] = str(exit_code)
        env["FETCH_TEST_SUMMARY"] = json.dumps(summary)
        return subprocess.run(
            [sys.executable, str(JOB_TOOL), "kaggle", "fetch", str(self.jobdir)],
            env=env, capture_output=True, text=True, timeout=10,
        )

    def test_failed_download_does_not_publish_cached_summary(self):
        cached = {"job": "stale-raw-output", "sha": "old", "ok": True}
        (self.raw / "summary.json").write_text(json.dumps(cached), encoding="utf-8")
        previous = '{"job": "previous-reviewed-result", "ok": false}\n'
        self.summary.write_text(previous, encoding="utf-8")

        result = self.fetch(exit_code=7)

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.summary.read_text(encoding="utf-8"), previous)
        self.assertNotIn("summary.json ->", result.stdout)
        self.assertNotIn("stale-raw-output", result.stdout)
        self.assertIn("download failed", result.stdout + result.stderr)

    def test_failed_download_without_cache_exits_nonzero(self):
        result = self.fetch(exit_code=7)

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.summary.exists())
        self.assertIn("download failed", result.stdout + result.stderr)

    def test_successful_download_publishes_fresh_summary(self):
        fresh = {"job": "fresh-output", "sha": "new", "ok": True}

        result = self.fetch(exit_code=0, summary=fresh)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(self.summary.read_text(encoding="utf-8")), fresh)
        self.assertIn("summary.json ->", result.stdout)


if __name__ == "__main__":
    unittest.main()
