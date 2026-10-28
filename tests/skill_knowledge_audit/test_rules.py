from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from .helpers import BENCH, REPO, SKILL_ROOT, load_json, write

from ska_impl.common import AuditError
from ska_impl.rules import (
    CLASSIFICATIONS, _classification, _verify_fixture_quotes, load_fixtures,
    load_rules_catalog, run_rules, verify_catalog_evidence,
)

PACKAGE = REPO / "easycirq" / "scripts" / "skill_knowledge_audit"
RULES_CATALOG = PACKAGE / "catalog" / "rules.json"
FIXTURES = BENCH / "fixtures" / "rule-pairs.json"


class Fixtures(unittest.TestCase):
    def test_all_fixture_classes_are_classified(self):
        fixtures = load_fixtures(FIXTURES)
        self.assertGreaterEqual(len(fixtures["pairs"]), 12)
        categories = set()
        for pair in fixtures["pairs"]:
            actual = _classification(pair["a"]["text"], pair["b"]["text"])
            self.assertEqual(actual, pair["expected"], pair["pair_id"])
            categories.add(pair["expected"])
        self.assertEqual(categories, CLASSIFICATIONS)

    def test_fixture_quotes_match_the_baseline(self):
        fixtures = load_fixtures(FIXTURES)
        self.assertEqual(_verify_fixture_quotes(fixtures["pairs"], SKILL_ROOT),
                         [])

    def test_fewer_than_twelve_pairs_is_rejected(self):
        data = load_json(FIXTURES)
        data["pairs"] = data["pairs"][:11]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixtures.json"
            write(path, json.dumps(data))
            with self.assertRaises(AuditError):
                load_fixtures(path)

    def test_tampered_fixture_quote_is_detected(self):
        data = load_json(FIXTURES)
        tampered = copy.deepcopy(data)
        tampered["pairs"][1]["a"]["text"] = "definitely not on that line"
        mismatches = _verify_fixture_quotes(tampered["pairs"], SKILL_ROOT)
        self.assertTrue(mismatches)


class RulesCatalog(unittest.TestCase):
    def test_catalog_has_rules_relations_and_no_confirmed_conflict(self):
        catalog = load_rules_catalog(RULES_CATALOG)
        self.assertEqual(len(catalog["rules"]), 12)
        self.assertEqual(len(catalog["relations"]), 10)
        self.assertFalse(any(relation["classification"] == "true_conflict"
                             for relation in catalog["relations"]))
        self.assertEqual(verify_catalog_evidence(catalog, SKILL_ROOT), [])
        ids = [rule["rule_id"] for rule in catalog["rules"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_duplicate_rule_id_is_rejected(self):
        data = load_json(RULES_CATALOG)
        data["rules"].append(copy.deepcopy(data["rules"][0]))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rules.json"
            write(path, json.dumps(data))
            with self.assertRaises(AuditError):
                load_rules_catalog(path)

    def test_empty_rules_is_a_failure_not_a_pass(self):
        data = load_json(RULES_CATALOG)
        data["rules"] = []
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rules.json"
            write(path, json.dumps(data))
            with self.assertRaises(AuditError):
                load_rules_catalog(path)

    def test_quote_mismatch_fails_the_catalog(self):
        data = load_json(RULES_CATALOG)
        data["rules"][0]["text"] = "this quote is not in SKILL.md"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rules.json"
            write(path, json.dumps(data))
            with self.assertRaises(AuditError):
                run_rules(SKILL_ROOT, catalog_path=path,
                          fixtures_path=FIXTURES)


class EndToEnd(unittest.TestCase):
    def test_rules_command_outputs_candidates_and_fixture_accuracy(self):
        result = run_rules(SKILL_ROOT, catalog_path=RULES_CATALOG,
                           fixtures_path=FIXTURES, strict=True)
        self.assertTrue(result["ok"])
        self.assertEqual(result["counts"]["rules"], 12)
        self.assertEqual(result["counts"]["reviewed_relations"], 10)
        self.assertEqual(result["counts"]["confirmed_conflicts"], 0)
        self.assertGreater(result["counts"]["machine_candidates"], 100)
        self.assertEqual(result["fixtures"]["accuracy"], 1.0)
        for candidate in result["candidates"]:
            self.assertEqual(candidate["classification"], "candidate")
        self.assertTrue(result["not_proof"])


if __name__ == "__main__":
    unittest.main()
