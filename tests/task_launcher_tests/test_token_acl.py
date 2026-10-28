"""Token-file permission hardening (#91): POSIX 0600 and Windows ACL."""

from __future__ import annotations

import os
import subprocess
import unittest

from .support import LauncherProcess


@unittest.skipUnless(os.name == "nt", "Windows ACL test")
class WindowsTokenAclTests(unittest.TestCase):
    def test_token_file_is_restricted_to_current_user(self) -> None:
        # generated token and a pre-existing token both get hardened (upgrade path)
        for fixed_token in (True, False):
            with self.subTest(fixed_token=fixed_token):
                launcher = LauncherProcess(fixed_token=fixed_token)
                self.addCleanup(launcher.close)
                path = launcher.token_file
                self.assertTrue(path.is_file())
                completed = subprocess.run(
                    ["icacls", str(path)],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=30,
                )
                acl = ((completed.stdout or "") + (completed.stderr or "")).upper()
                self.assertNotIn("BUILTIN\\USERS", acl, acl)
                self.assertNotIn("EVERYONE", acl, acl)
                # SYSTEM + Administrators + the current (ASCII) user name are kept;
                # the machine part may decode as mojibake under a non-UTF8 OEM
                # codepage, so only assert on the stable ASCII pieces.
                self.assertIn("NT AUTHORITY\\SYSTEM:(F)", acl, acl)
                self.assertIn("BUILTIN\\ADMINISTRATORS:(F)", acl, acl)
                self.assertIn(
                    f"\\{os.environ.get('USERNAME', '').upper()}:(F)",
                    acl,
                    acl,
                )


@unittest.skipIf(os.name == "nt", "POSIX token mode test")
class PosixTokenModeTests(unittest.TestCase):
    def test_generated_token_file_is_0600(self) -> None:
        launcher = LauncherProcess(fixed_token=False)
        self.addCleanup(launcher.close)
        mode = launcher.token_file.stat().st_mode & 0o777
        self.assertEqual(mode, 0o600, oct(mode))


if __name__ == "__main__":
    unittest.main()
