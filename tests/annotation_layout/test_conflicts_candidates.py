import json
import tempfile
import unittest
from pathlib import Path

try:
    from . import helpers
except ImportError:
    import helpers

from annotation_layout.candidates import generate_candidates, generate_for
from annotation_layout.conflicts import Evaluator, evaluate_assignment, hard_violations
from annotation_layout.schema import load_input, validate_input


class ConflictTest(unittest.TestCase):
    def test_real_fixture_current_hard_conflicts(self):
        inp = load_input(helpers.REAL)
        violations = evaluate_assignment(inp, {})
        hard = [item for item in violations if item.is_hard]
        codes = sorted(item.code for item in hard)
        self.assertEqual(codes, ["text_symbol_overlap", "text_wire_intrusion",
                                 "text_wire_intrusion"])
        self.assertIn("8bd5a6b179fa7148", {obj for item in hard for obj in item.objects})
        self.assertIn("ad6ce27bf74e95f9", {obj for item in hard for obj in item.objects})

    def test_own_wire_edge_contact_is_info_but_body_intrusion_is_hard(self):
        annotation = helpers.annotation(
            "L1", "net_label", "VREF", [100, 100, 140, 110],
            translate="supported", net="VREF", anchor_id="W1")
        wire = helpers.wire("W1", [(90, 100.5), (160, 100.5)])
        document = helpers.mini_input(annotations=[annotation], wires=[wire])
        document["host"]["capabilities"]["net_label_detach"] = "supported"
        inp = validate_input(document)
        evaluator = Evaluator(inp)
        edge = evaluator.static_violations(inp.annotation("L1"), inp.annotation("L1").current.bbox)
        self.assertIn("label_own_wire_edge_contact", {item.code for item in edge})
        self.assertFalse(any(item.is_hard for item in edge))
        # A wire through the glyph body must stay hard, even for the own wire.
        body_wire = helpers.wire("W1", [(90, 105), (160, 105)])
        document = helpers.mini_input(annotations=[annotation], wires=[body_wire])
        document["host"]["capabilities"]["net_label_detach"] = "supported"
        inp = validate_input(document)
        violations = Evaluator(inp).static_violations(
            inp.annotation("L1"), inp.annotation("L1").current.bbox)
        self.assertTrue(any(item.code == "text_wire_intrusion" and item.is_hard
                            for item in violations))

    def test_own_symbol_edge_contact_tolerance(self):
        ann = helpers.annotation("V1", "value", "10k", [100, 100, 120, 110],
                                 owner_id="C1")
        component = helpers.component("C1", [100, 90, 140, 101], "R1")
        document = helpers.mini_input(annotations=[ann], components=[component])
        document["constraints"]["self_text_contact_tolerance"] = 1.0
        inp = validate_input(document)
        violations = Evaluator(inp).static_violations(inp.annotation("V1"),
                                                       inp.annotation("V1").current.bbox)
        self.assertIn("symbol_text_edge_contact", {item.code for item in violations})
        self.assertFalse(any(item.is_hard for item in violations))
        # Deeper overlap is a hard conflict, not excused by ownership.
        deep = helpers.annotation("V1", "value", "10k", [100, 96, 120, 106],
                                  owner_id="C1")
        document = helpers.mini_input(annotations=[deep], components=[component])
        inp = validate_input(document)
        violations = Evaluator(inp).static_violations(inp.annotation("V1"),
                                                       inp.annotation("V1").current.bbox)
        self.assertTrue(any(item.code == "text_symbol_overlap" and item.is_hard
                            for item in violations))

    def test_flat_segments_are_independent(self):
        # flat-segments geometry must be split before conversion; every segment is
        # judged independently and no diagonal is invented between segments.
        annotation = helpers.annotation("A1", "free_text", "note", [100, 100, 160, 112])
        wire = helpers.wire("W1", [(100, 90), (100, 105), (160, 105), (160, 90)])
        document = helpers.mini_input(annotations=[annotation], wires=[wire])
        inp = validate_input(document)
        violations = Evaluator(inp).static_violations(inp.annotation("A1"),
                                                       inp.annotation("A1").current.bbox)
        intrusion = [item for item in violations if item.code == "text_wire_intrusion"]
        self.assertEqual(len(intrusion), 1)  # only the horizontal segment crosses
        self.assertEqual(intrusion[0].detail["segment"],
                         [[100.0, 105.0], [160.0, 105.0]])

    def test_candidate_generation_is_bounded_on_grid_and_rigid(self):
        inp = load_input(helpers.synthetic("rotated"))
        ann = inp.annotation("A1")
        domain = generate_for(inp, ann)
        self.assertGreater(len(domain), 1)
        grid = ann.constraints.grid
        for candidate in domain:
            self.assertTrue(abs((candidate.dx / grid) - round(candidate.dx / grid)) < 1e-9)
            self.assertTrue(abs((candidate.dy / grid) - round(candidate.dy / grid)) < 1e-9)
            self.assertLessEqual(round(candidate.displacement, 9),
                                 ann.constraints.max_displacement + 1e-9)
            self.assertAlmostEqual(candidate.bbox.width, ann.current.bbox.width)
            self.assertAlmostEqual(candidate.bbox.height, ann.current.bbox.height)
            self.assertEqual(ann.current.rotation_deg, 90.0)  # never changed
        self.assertEqual(domain, generate_for(inp, ann))  # deterministic

    def test_candidate_domains_for_fixed_and_unsupported_roles(self):
        inp = load_input(helpers.synthetic("net-anchor"))
        domains = generate_candidates(inp)
        self.assertEqual(domains.get("A1", []), [])
        real = load_input(helpers.REAL)
        domains = generate_candidates(real)
        self.assertEqual(len(domains), 42)
        # a value next to its owner has a candidate that clears the body overlap
        candidates = domains["8bd5a6b179fa7148"]
        self.assertTrue(any(candidate.dy < 0 for candidate in candidates))

    def test_candidate_truncation_is_recorded(self):
        inp = load_input(helpers.synthetic("dense"))
        from annotation_layout.model import SearchStats
        stats = SearchStats()
        domains = generate_candidates(inp, stats=stats)
        self.assertGreater(stats.candidates_truncated, 0)
        self.assertEqual(stats.candidates_generated,
                         sum(len(items) for items in domains.values()))


if __name__ == "__main__":
    unittest.main()
