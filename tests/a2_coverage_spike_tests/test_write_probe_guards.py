"""Guard tests for the authorization-gated write probe (offline; EDA never starts)."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import _bootstrap  # noqa: F401

import probe_writes as probe

SCRIPT = _bootstrap.SPIKE_DIR / "probe_writes.py"


def make_auth(tmp: Path, fixture: Path, **overrides) -> Path:
    data = {
        "schema": probe.AUTH_SCHEMA,
        "granted_by": "jlc",
        "granted_at": "2026-10-28T12:40:00+08:00",
        "scope": ["W04", "W05", "W09"],
        "fixture_source": fixture.as_posix(),
        "project_root": (tmp / "probe-root").as_posix(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat(),
        "notes": "unit test",
    }
    data.update(overrides)
    path = tmp / "authorization.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


class AuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="a2-auth-test-"))
        self.fixture = self.tmp / "fixture.eprj2"
        self.fixture.write_bytes(b"dummy project")
        self.auth = make_auth(self.tmp, self.fixture)

    def test_valid_authorization_accepted(self):
        data, problems = probe.validate_authorization(self.auth, self.fixture)
        self.assertEqual(problems, [])
        self.assertEqual(data["granted_by"], "jlc")

    def test_missing_granted_by_rejected(self):
        path = make_auth(self.tmp, self.fixture, granted_by="")
        _, problems = probe.validate_authorization(path, self.fixture)
        self.assertTrue(any("granted_by" in p for p in problems))

    def test_scope_must_cover_all_three(self):
        path = make_auth(self.tmp, self.fixture, scope=["W04", "W09"])
        _, problems = probe.validate_authorization(path, self.fixture)
        self.assertTrue(any("scope" in p for p in problems))

    def test_project_root_outside_temp_rejected(self):
        path = make_auth(self.tmp, self.fixture, project_root="C:/Users/jlc/Documents/not-temp")
        _, problems = probe.validate_authorization(path, self.fixture)
        self.assertTrue(any("project_root" in p for p in problems))

    def test_fixture_outside_temp_rejected(self):
        outside = Path("C:/Users/jlc/Documents/big-user-project.eprj2")
        path = make_auth(self.tmp, outside, fixture_source=outside.as_posix())
        _, problems = probe.validate_authorization(path, outside)
        self.assertTrue(any("temp directory" in p for p in problems))

    def test_fixture_mismatch_rejected(self):
        other = self.tmp / "other.eprj2"
        other.write_bytes(b"x")
        path = make_auth(self.tmp, other)
        _, problems = probe.validate_authorization(path, self.fixture)
        self.assertTrue(any("does not match" in p for p in problems))

    def test_expired_authorization_rejected(self):
        path = make_auth(
            self.tmp,
            self.fixture,
            expires_at=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        )
        _, problems = probe.validate_authorization(path, self.fixture)
        self.assertTrue(any("expired" in p for p in problems))

    def test_bad_schema_rejected(self):
        path = make_auth(self.tmp, self.fixture, schema="something-else")
        _, problems = probe.validate_authorization(path, self.fixture)
        self.assertTrue(any("schema" in p for p in problems))

    def test_missing_authorization_file_exits_two(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--dry-run", "--fixture", str(self.fixture),
             "--authorization", str(self.tmp / "nope.json")],
            capture_output=True, text=True, encoding="utf-8", timeout=120,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("authorization file not found", result.stderr)

    def test_missing_fixture_exits_two(self):
        missing = self.tmp / "nope.eprj2"
        auth = make_auth(self.tmp, missing)
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--dry-run", "--fixture", str(missing),
             "--authorization", str(auth)],
            capture_output=True, text=True, encoding="utf-8", timeout=120,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("fixture not found", result.stderr)


class DryRunTests(unittest.TestCase):
    def test_dry_run_validates_without_starting_eda(self):
        tmp = Path(tempfile.mkdtemp(prefix="a2-probe-dry-"))
        fixture = tmp / "fixture.eprj2"
        fixture.write_bytes(b"dummy")
        auth = make_auth(tmp, fixture)
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--dry-run", "--fixture", str(fixture),
             "--authorization", str(auth), "--evidence-date", "2026-10-28"],
            capture_output=True, text=True, encoding="utf-8", timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("dry-run: authorization valid", result.stdout)
        self.assertIn("no EDA started", result.stdout)
        self.assertIn("write-probe-passed.json", result.stdout)

    def test_dry_run_does_not_write_marker(self):
        marker = _bootstrap.EVIDENCE_DIR / "write-probe-passed.json"
        if marker.exists():
            self.skipTest("a real write probe already passed; marker is expected")
        tmp = Path(tempfile.mkdtemp(prefix="a2-probe-dry2-"))
        fixture = tmp / "fixture.eprj2"
        fixture.write_bytes(b"dummy")
        auth = make_auth(tmp, fixture)
        subprocess.run(
            [sys.executable, str(SCRIPT), "--dry-run", "--fixture", str(fixture),
             "--authorization", str(auth), "--evidence-date", "2026-10-28"],
            capture_output=True, text=True, encoding="utf-8", timeout=120,
        )
        self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
