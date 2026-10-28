import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "easycirq" / "scripts" / "eda_cache.py"


class EdaCacheCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="eda-cache-")
        self.root = Path(self.tmp.name)
        self.cache = self.root / "cache"
        self.value = self.root / "value.json"
        self.value.write_text(json.dumps({"page": "P1", "components": 16}), encoding="utf-8")
        self.params = json.dumps({"page": "P1"})

    def tearDown(self):
        self.tmp.cleanup()

    def run_tool(self, *args):
        proc = subprocess.run([sys.executable, str(SCRIPT), *args],
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=60)
        return proc, json.loads(proc.stdout)

    def put(self, version_tag="save-1", cli_version="1.14.0", params=None):
        return self.run_tool(
            "put", "--cache", str(self.cache), "--project", "proj",
            "--document", "doc", "--action", "schematic.components.list",
            "--params", params or self.params, "--version-tag", version_tag,
            "--cli-version", cli_version, "--value", str(self.value))

    def get(self, version_tag="save-1", cli_version="1.14.0", ttl=None, params=None):
        args = ["get", "--cache", str(self.cache), "--project", "proj",
                "--document", "doc", "--action", "schematic.components.list",
                "--params", params or self.params, "--version-tag", version_tag]
        if cli_version is not None:
            args += ["--cli-version", cli_version]
        if ttl is not None:
            args += ["--ttl-seconds", str(ttl)]
        return self.run_tool(*args)

    def entry_path(self):
        files = list(self.cache.glob("*.json"))
        self.assertEqual(len(files), 1)
        return files[0]

    def test_put_then_get_hits(self):
        proc, report = self.put()
        self.assertEqual(proc.returncode, 0, proc.stdout)
        proc, report = self.get()
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(report["status"], "hit")
        self.assertEqual(report["value"]["components"], 16)

    def test_version_tag_mismatch_is_miss(self):
        self.put()
        proc, report = self.get(version_tag="save-2")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(report["status"], "miss")
        self.assertEqual(report["reason"], "version_tag_mismatch")

    def test_cli_version_mismatch_is_miss(self):
        self.put()
        proc, report = self.get(cli_version="1.15.0")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(report["reason"], "cli_version_mismatch")

    def test_ttl_expired_is_miss(self):
        self.put()
        entry = self.entry_path()
        data = json.loads(entry.read_text(encoding="utf-8"))
        data["storedAt"] = data["storedAt"] - 100
        entry.write_text(json.dumps(data), encoding="utf-8")
        proc, report = self.get(ttl=10)
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(report["reason"], "ttl_expired")

    def test_corrupt_entry_is_miss(self):
        self.put()
        self.entry_path().write_text("{not json", encoding="utf-8")
        proc, report = self.get()
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(report["reason"], "corrupt_entry")

    def test_invalidate_by_document(self):
        self.put()
        proc, report = self.run_tool(
            "invalidate", "--cache", str(self.cache),
            "--project", "proj", "--document", "doc")
        self.assertEqual(report["removed"], 1)
        proc, report = self.get()
        self.assertEqual(report["reason"], "not_found")

    def test_different_params_is_a_different_key(self):
        self.put()
        proc, report = self.get(params=json.dumps({"page": "P2"}))
        self.assertEqual(report["reason"], "not_found")

    def test_tool_version_is_part_of_the_key(self):
        proc, report = self.run_tool(
            "put", "--cache", str(self.cache), "--project", "proj",
            "--document", "doc", "--action", "pcb.dump",
            "--params", self.params, "--version-tag", "save-1",
            "--cli-version", "1.14.0", "--tool-version", "tool-a",
            "--value", str(self.value))
        self.assertEqual(proc.returncode, 0, proc.stdout)
        proc, report = self.get_tool_version("tool-a")
        self.assertEqual(report["status"], "hit")
        proc, report = self.get_tool_version("tool-b")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(report["reason"], "not_found")

    def get_tool_version(self, version):
        return self.run_tool(
            "get", "--cache", str(self.cache), "--project", "proj",
            "--document", "doc", "--action", "pcb.dump",
            "--params", self.params, "--version-tag", "save-1",
            "--cli-version", "1.14.0", "--tool-version", version)

    def test_stats(self):
        self.put()
        proc, report = self.run_tool("stats", "--cache", str(self.cache))
        self.assertEqual(report["entries"], 1)
        self.assertEqual(report["projects"], 1)
        self.assertEqual(report["documents"], 1)


if __name__ == "__main__":
    unittest.main()
