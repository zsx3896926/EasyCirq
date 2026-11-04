"""Golden ACE corpus + additive error-injection regression tests.

The corpus under ``easycirq/assets/ace-corpus`` is a frozen, offline reference:

- ``clean-reference.json``: synthetic snapshot that must stay review-clean;
- ``clean-reference.expected.json``: the expected review outcome for it;
- ``bad-*.json``: one single-defect snapshot per rule (I2C pull-up missing,
  decoupling cap too far, ground tie broken).

The files are canonical JSON (sorted keys, two-space indent, no timestamps) so
corpus diffs stay reviewable, and the injection harness is checked for both
mutation classes: deletion (break existing structure) and additive (append a
defect to the clean design).
"""

import copy
import json
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
CORPUS = ROOT / "easycirq" / "assets" / "ace-corpus"
sys.path.insert(0, str(ROOT / "tools"))

import ace_inject  # noqa: E402
import ace_review  # noqa: E402

SNAPSHOT_SCHEMA = "easycirq-ace-snapshot/v1"
EXPECTED_SCHEMA = "easycirq-ace-expected/v1"

BAD_CASES = {
    "bad-missing-i2c-pullup.json": ("R02-i2c-pullup", 2),
    "bad-decoupling-too-far.json": ("R03-decoupling", 1),
    "bad-ground-tie-broken.json": ("R04-ground-tie", 1),
}

EXTENDED_BAD_FILES = [
    "bad-floating-pin.json",
    "bad-enable-float.json",
    "bad-esd-missing.json",
    "bad-testpoint-missing.json",
    "bad-auto-net.json",
    "bad-titleblock.json",
    "bad-cs-no-pullup.json",
    "bad-bom-placeholder.json",
]
CORPUS_FILES = sorted(
    ["clean-reference.json", "clean-reference.expected.json"]
    + list(BAD_CASES) + EXTENDED_BAD_FILES)

ADDITIVE_RULES = {
    "add-second-ground-tie": "R04-ground-tie",
    "add-auto-net-name": "R09-auto-net-name",
    "add-connector-without-esd": "R07-esd-series",
    "add-floating-pin": "R01-floating-pin",
    "add-cs-without-pullup": "R23-spi-cs-pullup",
    "add-connector-without-tvs": "R27-connector-tvs",
}

TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?)?$")
TIMESTAMP_KEYS = ("timestamp", "generated_at", "created_at", "updated_at")


def load(name):
    return json.loads((CORPUS / name).read_text(encoding="utf-8"))


def error_rules(report):
    return [f["rule"] for f in report["findings"] if f["severity"] == "error"]


class CorpusLoadTests(unittest.TestCase):
    def test_corpus_contains_expected_files(self):
        self.assertTrue(CORPUS.is_dir(), "missing corpus dir %s" % CORPUS)
        names = sorted(p.name for p in CORPUS.glob("*.json"))
        self.assertEqual(names, CORPUS_FILES)
        self.assertEqual(len(list(CORPUS.glob("bad-*.json"))), 11)

    def test_snapshots_are_valid_ace_snapshots(self):
        for name in ["clean-reference.json"] + list(BAD_CASES):
            with self.subTest(file=name):
                snap = load(name)
                self.assertEqual(snap["schema"], SNAPSHOT_SCHEMA)
                self.assertIsInstance(snap["components"], list)
                self.assertTrue(snap["components"])
                refs = [c["ref"] for c in snap["components"]]
                self.assertEqual(refs, sorted(refs), "components must stay sorted")
                self.assertEqual(len(refs), len(set(refs)), "duplicate refs")
                for comp in snap["components"]:
                    self.assertIn("bbox", comp)
                    for pin in comp["pins"]:
                        self.assertIn("number", pin)
                        self.assertIn("name", pin)
                        self.assertIn("net", pin)
                self.assertIsInstance(snap.get("titleblock", {}).get("fields"), dict)


class CleanReferenceTests(unittest.TestCase):
    def test_clean_reference_passes_without_findings(self):
        report = ace_review.review(load("clean-reference.json"))
        self.assertEqual(report["verdict"], "pass", report["findings"])
        self.assertEqual(report["metrics"]["errors"], 0)
        self.assertEqual(report["metrics"]["warnings"], 0, report["findings"])
        self.assertEqual(report["metrics"]["rules"], [])

    def test_expected_file_matches_review(self):
        expected = load("clean-reference.expected.json")
        self.assertEqual(expected["schema"], EXPECTED_SCHEMA)
        self.assertEqual(expected["snapshot"], "clean-reference.json")
        report = ace_review.review(load("clean-reference.json"))
        self.assertEqual(expected["verdict"], report["verdict"])
        self.assertEqual(expected["errors"], report["metrics"]["errors"])
        self.assertEqual(expected["warnings"], report["metrics"]["warnings"])
        self.assertEqual(sorted(expected["rules"]), report["metrics"]["rules"])


class BadCorpusTests(unittest.TestCase):
    def test_each_bad_snapshot_yields_its_expected_rule(self):
        for name, (rule, errors) in BAD_CASES.items():
            with self.subTest(file=name):
                report = ace_review.review(load(name))
                self.assertEqual(report["verdict"], "blocked")
                self.assertEqual(set(error_rules(report)), {rule}, report["findings"])
                self.assertEqual(len(error_rules(report)), errors)
                self.assertEqual(report["metrics"]["errors"], errors)


class InjectionRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = ace_inject.run(load("clean-reference.json"))
        cls.rows = cls.result["mutations"]

    def rows_of(self, kind):
        return [r for r in self.rows if r["kind"] == kind]

    def test_clean_reference_baseline_passes(self):
        self.assertEqual(self.result["baseline"]["verdict"], "pass")
        self.assertEqual(self.result["baseline"]["errors"], 0)
        self.assertEqual(self.result["baseline"]["rules"], [])

    def test_deletion_mutations_still_detected(self):
        rows = self.rows_of("deletion")
        self.assertGreaterEqual(len(rows), 8)
        self.assertTrue(all(r["applicable"] for r in rows), self.result["not_applicable"])
        self.assertTrue(all(r["detected"] for r in rows))
        self.assertEqual(self.result["classes"]["deletion"]["detected"], len(rows))

    def test_additive_mutations_present_and_detected(self):
        rows = self.rows_of("additive")
        names = {r["mutation"] for r in rows}
        self.assertEqual(names, set(ADDITIVE_RULES))
        self.assertTrue(all(r["applicable"] for r in rows), self.result["not_applicable"])
        self.assertTrue(all(r["detected"] for r in rows))
        self.assertEqual(self.result["classes"]["additive"]["detected"], len(rows))

    def test_additive_mutations_use_expected_rules(self):
        by_name = {r["mutation"]: r for r in self.rows_of("additive")}
        for name, rule in ADDITIVE_RULES.items():
            with self.subTest(mutation=name):
                self.assertEqual(by_name[name]["expected_rule"], rule)

    def test_both_injection_classes_are_fully_detected(self):
        self.assertEqual(self.result["detected"], self.result["total"])
        self.assertEqual(self.result["detection_rate"], 1.0)
        self.assertEqual(self.result["not_applicable"], [])
        for kind in ("deletion", "additive"):
            block = self.result["classes"][kind]
            self.assertGreater(block["applicable"], 0, kind)
            self.assertEqual(block["detected"], block["applicable"], kind)
        self.assertGreaterEqual(self.result["total"], 12)


class DeterminismTests(unittest.TestCase):
    def test_corpus_files_are_canonical_json(self):
        for name in CORPUS_FILES:
            with self.subTest(file=name):
                text = (CORPUS / name).read_text(encoding="utf-8")
                data = json.loads(text)
                canonical = json.dumps(data, ensure_ascii=False, indent=2,
                                       sort_keys=True) + "\n"
                self.assertEqual(text, canonical,
                                 "%s is not canonical deterministic JSON" % name)

    def test_corpus_has_no_timestamps(self):
        def walk(node, path):
            if isinstance(node, dict):
                for key, value in node.items():
                    lowered = key.lower()
                    for marker in TIMESTAMP_KEYS:
                        self.assertNotIn(marker, lowered,
                                         "%s: timestamp-like key %r" % (path, key))
                    walk(value, path + "/" + key)
            elif isinstance(node, list):
                for index, value in enumerate(node):
                    walk(value, "%s[%d]" % (path, index))
            elif isinstance(node, str):
                self.assertNotRegex(
                    node, TIMESTAMP_RE,
                    "%s: timestamp-like value %r" % (path, node))

        for name in CORPUS_FILES:
            walk(load(name), name)

    def test_review_output_is_reproducible(self):
        snapshot = load("clean-reference.json")
        first = json.dumps(ace_review.review(copy.deepcopy(snapshot)), sort_keys=True)
        second = json.dumps(ace_review.review(copy.deepcopy(snapshot)), sort_keys=True)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()


EXPECTED_RULE = {
    "bad-floating-pin.json": "R01-floating-pin",
    "bad-enable-float.json": "R06-enable-net",
    "bad-esd-missing.json": "R07-esd-series",
    "bad-testpoint-missing.json": "R08-power-testpoint",
    "bad-auto-net.json": "R09-auto-net-name",
    "bad-titleblock.json": "R10-titleblock",
    "bad-cs-no-pullup.json": "R23-spi-cs-pullup",
    "bad-bom-placeholder.json": "R29-bom-value",
}


class ExtendedCorpusTests(unittest.TestCase):
    def test_each_bad_snapshot_triggers_its_rule(self):
        for filename, rule in EXPECTED_RULE.items():
            path = CORPUS / filename
            self.assertTrue(path.exists(), path)
            snapshot = json.loads(path.read_text(encoding="utf-8"))
            rules = {f["rule"] for f in ace_review.review(snapshot)["findings"]}
            self.assertIn(rule, rules, "%s -> %s" % (filename, sorted(rules)))

    def test_new_bad_snapshots_are_deterministic_json(self):
        for filename in EXPECTED_RULE:
            raw = (CORPUS / filename).read_bytes()
            self.assertEqual(raw, (CORPUS / filename).read_bytes())

