"""Tests for deterministic block role resolution and placement templates.

Synthetic fixtures only: a block manifest, an ACE snapshot and a resolved
standard-parts table are built in-memory, so the tests stay offline and do not
depend on the EDA daemon.
"""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.layout2 import role_resolver, templates  # noqa: E402

SNAPSHOT_SCHEMA = role_resolver.SNAPSHOT_SCHEMA
BLOCK_ID = "block.demo_audio"

# Manifest: two identical 22uF caps that only net topology can tell apart.
MANIFEST = {
    "id": BLOCK_ID,
    "parts": {
        "U": {"part": "ic.demo_amp", "qty": 1},
        "R": {"part": "res.10k", "qty": 1},
        "C_A": {"part": "cap.22uf", "qty": 1},
        "C_B": {"part": "cap.22uf", "qty": 1},
    },
    "internal_nets": [
        ["U.VDD", "C_A.1", "PORT:VDD"],
        ["U.GND", "C_A.2", "C_B.2", "PORT:GND"],
        ["U.OUT", "C_B.1"],
        ["U.IN", "R.2"],
        ["R.1", "PORT:IN"],
    ],
    "ports": {
        "VDD": {"dir": "in", "at": "U.VDD", "default_net": "5V"},
        "GND": {"dir": "in", "at": "U.GND", "default_net": "GND"},
        "IN": {"dir": "in", "at": "R.1", "default_net": "DAC_L"},
        "MODE": {"dir": "in", "at": "U.MODE", "default_net": "MODE_CFG"},
    },
}

RESOLVED_PARTS = {
    "ic.demo_amp": {"mpn": "IC-DEMO"},
    "res.10k": {"mpn": "RES-10K"},
    "cap.22uf": {"mpn": "CAP-22U"},
}


def pin(number, name, net):
    return {"number": str(number), "name": name, "net": net}


def comp(ref, mpn, bbox, pins, rotation=None):
    component = {
        "ref": ref,
        "mpn": mpn,
        "value": None,
        "bbox": {
            "minX": bbox[0],
            "minY": bbox[1],
            "maxX": bbox[2],
            "maxY": bbox[3],
        },
        "pins": pins,
    }
    if rotation is not None:
        component["rotation"] = rotation
    return component


def base_components():
    """U1/R1/C1/C2 placed and wired so only C_A -> C1, C_B -> C2 is valid."""
    return [
        comp(
            "U1",
            "IC-DEMO",
            (100, 100, 160, 160),
            [
                pin(1, "VDD", "5V"),
                pin(2, "GND", "GND"),
                pin(3, "OUT", "AMP_OUT"),
                pin(4, "IN", "IN_NET"),
                pin(5, "MODE", "MODE_NET"),
            ],
        ),
        comp("C1", "CAP-22U", (180, 100, 200, 120), [pin(1, "1", "5V"), pin(2, "2", "GND")], rotation=90),
        comp("C2", "CAP-22U", (180, 140, 200, 160), [pin(1, "1", "AMP_OUT"), pin(2, "2", "GND")]),
        comp("R1", "RES-10K", (220, 100, 240, 120), [pin(1, "1", "DAC_L"), pin(2, "2", "IN_NET")]),
    ]


def snapshot(components=None, **overrides):
    document = {
        "schema": SNAPSHOT_SCHEMA,
        "page": "p1",
        "components": components if components is not None else base_components(),
        "nets": [],
    }
    document.update(overrides)
    return document


def write_resolved(path, parts=None):
    path.write_text(json.dumps({"parts": parts if parts is not None else RESOLVED_PARTS}), encoding="utf-8")
    return path


class ResolverFixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.resolved_path = write_resolved(
            Path(self._tmp.name) / "standard-parts.resolved.json"
        )

    def resolve(self, manifest=None, snap=None):
        return role_resolver.resolve_roles(
            manifest if manifest is not None else copy.deepcopy(MANIFEST),
            snap if snap is not None else snapshot(),
            resolved_parts_path=self.resolved_path,
        )


class RoleResolverTests(ResolverFixture):
    def test_two_same_mpn_caps_are_distinguished_by_net_topology(self):
        result = self.resolve()
        self.assertEqual(result, {"U": "U1", "R": "R1", "C_A": "C1", "C_B": "C2"})
        self.assertEqual(list(result), ["U", "R", "C_A", "C_B"])

    def test_resolution_is_deterministic_and_order_independent(self):
        first = self.resolve()
        second = self.resolve()
        self.assertEqual(first, second)
        # Snapshot component order must not change the binding.
        shuffled = snapshot(list(reversed(base_components())))
        self.assertEqual(self.resolve(snap=shuffled), first)
        # Re-encoding the manifest keeps the same roles/order.
        reordered = copy.deepcopy(MANIFEST)
        reordered["internal_nets"] = list(reordered["internal_nets"])
        self.assertEqual(self.resolve(manifest=reordered), first)

    def test_ambiguous_roles_raise_a_clear_error(self):
        manifest = {
            "id": BLOCK_ID,
            "parts": {
                "U": {"part": "ic.demo_amp"},
                "C_A": {"part": "cap.22uf"},
                "C_B": {"part": "cap.22uf"},
            },
            "internal_nets": [
                ["U.VDD", "C_A.1", "PORT:VDD"],
                ["U.VDD", "C_B.1", "PORT:VDD"],
                ["U.GND", "C_A.2", "PORT:GND"],
                ["U.GND", "C_B.2", "PORT:GND"],
            ],
            "ports": {},
        }
        components = [
            comp("U1", "IC-DEMO", (100, 100, 160, 160), [pin(1, "VDD", "5V"), pin(2, "GND", "GND")]),
            comp("C1", "CAP-22U", (180, 100, 200, 120), [pin(1, "1", "5V"), pin(2, "2", "GND")]),
            comp("C2", "CAP-22U", (180, 140, 200, 160), [pin(1, "1", "5V"), pin(2, "2", "GND")]),
        ]
        with self.assertRaisesRegex(role_resolver.RoleResolutionError, "ambiguous role assignment"):
            self.resolve(manifest=manifest, snap=snapshot(components))

    def test_no_candidate_mpn_raises(self):
        manifest = copy.deepcopy(MANIFEST)
        manifest["parts"]["R"]["mpn"] = "RES-NOT-ON-PAGE"
        with self.assertRaisesRegex(role_resolver.RoleResolutionError, "no snapshot candidate"):
            self.resolve(manifest=manifest)

    def test_unresolved_mpn_rows_are_tolerated_unless_needed(self):
        resolved = dict(RESOLVED_PARTS)
        resolved["mcu.not_on_this_page"] = {"mpn": None}
        write_resolved(self.resolved_path, resolved)
        self.assertEqual(
            self.resolve(),
            {"U": "U1", "R": "R1", "C_A": "C1", "C_B": "C2"},
        )
        resolved["res.10k"] = {"mpn": None}
        write_resolved(self.resolved_path, resolved)
        with self.assertRaisesRegex(role_resolver.RoleResolutionError, "no resolved MPN"):
            self.resolve()

    def test_missing_resolved_part_key_raises(self):
        resolved = dict(RESOLVED_PARTS)
        del resolved["res.10k"]
        write_resolved(self.resolved_path, resolved)
        with self.assertRaisesRegex(role_resolver.RoleResolutionError, "missing from the resolved parts"):
            self.resolve()

    def test_resolved_path_is_optional_and_part_key_may_be_the_mpn(self):
        manifest = {
            "id": BLOCK_ID,
            "parts": {
                "U": {"part": "IC-DEMO"},
                "R": {"part": "RES-10K"},
                "C_A": {"part": "CAP-22U"},
                "C_B": {"part": "CAP-22U"},
            },
            "internal_nets": copy.deepcopy(MANIFEST["internal_nets"]),
        }
        result = role_resolver.resolve_roles(manifest, snapshot())
        self.assertEqual(result, {"U": "U1", "R": "R1", "C_A": "C1", "C_B": "C2"})

    def test_without_resolved_table_a_snapshot_value_can_match(self):
        manifest = {
            "id": BLOCK_ID,
            "parts": {"U": {"part": "IC-DEMO"}, "C_A": {"part": "CAP-22U"}},
            "internal_nets": [["U.VDD", "C_A.1"]],
        }
        components = [
            comp("U1", "IC-DEMO", (100, 100, 160, 160), [pin(1, "VDD", "5V")]),
            {"ref": "C1", "mpn": None, "value": "CAP-22U",
             "bbox": {"minX": 180, "minY": 100, "maxX": 200, "maxY": 120},
             "pins": [pin(1, "1", "5V")]},
        ]
        self.assertEqual(
            role_resolver.resolve_roles(manifest, snapshot(components)),
            {"U": "U1", "C_A": "C1"},
        )

    def test_one_designator_cannot_serve_two_roles(self):
        manifest = {
            "id": BLOCK_ID,
            "parts": {
                "U": {"part": "ic.demo_amp"},
                "U_SPARE": {"part": "ic.demo_amp"},
            },
            "internal_nets": [["U.VDD", "U_SPARE.VDD"]],
        }
        components = [
            comp("U1", "IC-DEMO", (100, 100, 160, 160), [pin(1, "VDD", "5V")]),
        ]
        with self.assertRaisesRegex(role_resolver.RoleResolutionError, "no 1-1 role"):
            self.resolve(manifest=manifest, snap=snapshot(components))

    def test_quantity_must_be_one(self):
        manifest = copy.deepcopy(MANIFEST)
        manifest["parts"]["C_A"]["qty"] = 2
        with self.assertRaisesRegex(role_resolver.RoleResolutionError, "exactly 1 per role"):
            self.resolve(manifest=manifest)

    def test_unknown_role_and_bad_pin_ref_are_rejected(self):
        manifest = copy.deepcopy(MANIFEST)
        manifest["internal_nets"].append(["Q.OUT", "R.1"])
        with self.assertRaisesRegex(role_resolver.RoleResolutionError, "unknown role 'Q'"):
            self.resolve(manifest=manifest)
        manifest = copy.deepcopy(MANIFEST)
        manifest["internal_nets"].append(["U.VDD"])
        # ("U.VDD" alone is a legal single-member net; use a malformed token instead.)
        manifest["internal_nets"][-1] = ["U"]
        with self.assertRaisesRegex(role_resolver.RoleResolutionError, "bad pin ref"):
            self.resolve(manifest=manifest)

    def test_snapshot_schema_and_duplicate_refs_are_rejected(self):
        with self.assertRaisesRegex(role_resolver.RoleResolutionError, "snapshot.schema"):
            self.resolve(snap=snapshot(schema="other/v1"))
        components = base_components() + [copy.deepcopy(base_components()[0])]
        with self.assertRaisesRegex(role_resolver.RoleResolutionError, "duplicate ref"):
            self.resolve(snap=snapshot(components))

    def test_missing_pin_on_candidate_means_no_assignment(self):
        # C1/C2 miss the pin referenced by the topology -> candidates are pruned.
        components = base_components()
        for component in components:
            if component["ref"] in ("C1", "C2"):
                component["pins"] = [item for item in component["pins"] if item["number"] != "1"]
        with self.assertRaisesRegex(role_resolver.RoleResolutionError, "none exposes the pins"):
            self.resolve(snap=snapshot(components))

    def test_star_pin_means_all_same_name_pins_in_parallel(self):
        manifest = {
            "id": BLOCK_ID,
            "parts": {"U": {"part": "ic.demo_amp"}, "C_A": {"part": "cap.22uf"}},
            "internal_nets": [["U.VDD*", "C_A.1", "PORT:VDD"]],
        }
        components = [
            comp("U1", "IC-DEMO", (100, 100, 160, 160), [
                pin(1, "VDD", "5V"),
                pin(2, "VDD", "5V"),
            ]),
            comp("C1", "CAP-22U", (180, 100, 200, 120), [pin(1, "1", "5V")]),
        ]
        self.assertEqual(
            self.resolve(manifest=manifest, snap=snapshot(components)),
            {"U": "U1", "C_A": "C1"},
        )

    def test_split_star_pins_break_the_topology(self):
        manifest = {
            "id": BLOCK_ID,
            "parts": {"U": {"part": "ic.demo_amp"}, "C_A": {"part": "cap.22uf"}},
            "internal_nets": [["U.VDD*", "C_A.1", "PORT:VDD"]],
        }
        components = [
            comp("U1", "IC-DEMO", (100, 100, 160, 160), [
                pin(1, "VDD", "5V"),
                pin(2, "VDD", "3V3"),  # same-name pads on different nets: not parallel
            ]),
            comp("C1", "CAP-22U", (180, 100, 200, 120), [pin(1, "1", "5V")]),
        ]
        with self.assertRaisesRegex(role_resolver.RoleResolutionError, "no 1-1 role"):
            self.resolve(manifest=manifest, snap=snapshot(components))

    def test_inconsistent_snapshot_topology_means_no_assignment(self):
        # Swap C1's nets so neither cap satisfies its constraining net.
        components = base_components()
        for component in components:
            if component["ref"] == "C1":
                component["pins"] = [pin(1, "1", "WRONG"), pin(2, "2", "WRONG")]
        with self.assertRaisesRegex(role_resolver.RoleResolutionError, "no 1-1 role"):
            self.resolve(snap=snapshot(components))

    def test_missing_resolved_file_is_reported(self):
        with self.assertRaisesRegex(role_resolver.RoleResolutionError, "cannot read resolved parts file"):
            role_resolver.resolve_roles(
                copy.deepcopy(MANIFEST), snapshot(),
                resolved_parts_path=Path(self._tmp.name) / "absent.json",
            )


class TemplateFixture(ResolverFixture):
    def setUp(self):
        super().setUp()
        self.role_map = self.resolve()

    def template(self, **kwargs):
        return templates.extract_template(
            BLOCK_ID, copy.deepcopy(MANIFEST), snapshot(), self.role_map, **kwargs
        )


class ExtractTemplateTests(TemplateFixture):
    def test_origin_is_anchor_part_centre(self):
        template = self.template()
        self.assertEqual(template["schema"], templates.TEMPLATE_SCHEMA)
        self.assertEqual(template["block"], BLOCK_ID)
        self.assertEqual(
            template["origin"],
            {"role": "U", "ref": "U1", "x": 130, "y": 130},
        )

    def test_parts_store_centre_offsets_and_relative_bboxes(self):
        template = self.template()
        parts = {part["role"]: part for part in template["parts"]}
        self.assertEqual(list(parts), ["U", "R", "C_A", "C_B"])
        self.assertEqual(parts["U"]["designator"], "U1")
        self.assertEqual((parts["U"]["dx"], parts["U"]["dy"]), (0, 0))
        self.assertEqual(parts["U"]["bbox"], {"minX": -30, "minY": -30, "maxX": 30, "maxY": 30})
        # R1 centre (230, 110) relative to U1 centre (130, 130).
        self.assertEqual((parts["R"]["dx"], parts["R"]["dy"]), (100, -20))
        self.assertEqual(parts["R"]["bbox"], {"minX": 90, "minY": -30, "maxX": 110, "maxY": -10})
        # C1 is rotated 90 in the snapshot; rotation is carried as metadata.
        self.assertEqual(parts["C_A"]["rotation"], 90)
        self.assertEqual(parts["C_B"]["rotation"], 0)
        self.assertEqual(
            template["bbox"], {"minX": -30, "minY": -30, "maxX": 110, "maxY": 30}
        )

    def test_pins_follow_port_default_nets_and_internal_net_names(self):
        template = self.template()
        self.assertEqual(
            template["pins"],
            [
                {"role": "U", "pin": "VDD", "net": "5V"},
                {"role": "C_A", "pin": "1", "net": "5V"},
                {"role": "U", "pin": "GND", "net": "GND"},
                {"role": "C_A", "pin": "2", "net": "GND"},
                {"role": "C_B", "pin": "2", "net": "GND"},
                {"role": "U", "pin": "OUT", "net": BLOCK_ID + "_N3"},
                {"role": "C_B", "pin": "1", "net": BLOCK_ID + "_N3"},
                {"role": "U", "pin": "IN", "net": BLOCK_ID + "_N4"},
                {"role": "R", "pin": "2", "net": BLOCK_ID + "_N4"},
                {"role": "R", "pin": "1", "net": "DAC_L"},
                # MODE port is not in internal_nets: single-pin fallback net.
                {"role": "U", "pin": "MODE", "net": "MODE_CFG"},
            ],
        )

    def test_origin_role_can_be_overridden(self):
        template = self.template(origin_role="R")
        self.assertEqual(template["origin"], {"role": "R", "ref": "R1", "x": 230, "y": 110})
        parts = {part["role"]: part for part in template["parts"]}
        self.assertEqual((parts["U"]["dx"], parts["U"]["dy"]), (-100, 20))
        with self.assertRaisesRegex(templates.BlockTemplateError, "origin_role"):
            self.template(origin_role="Q")

    def test_extraction_is_deterministic(self):
        self.assertEqual(self.template(), self.template())

    def test_role_map_validation(self):
        with self.assertRaisesRegex(templates.BlockTemplateError, "missing designator"):
            templates.extract_template(BLOCK_ID, copy.deepcopy(MANIFEST), snapshot(), {"U": "U1"})
        extra = dict(self.role_map)
        extra["Q"] = "Q1"
        with self.assertRaisesRegex(templates.BlockTemplateError, "unknown role"):
            templates.extract_template(BLOCK_ID, copy.deepcopy(MANIFEST), snapshot(), extra)
        duplicate = dict(self.role_map)
        duplicate["R"] = duplicate["U"]
        with self.assertRaisesRegex(templates.BlockTemplateError, "more than one role"):
            templates.extract_template(BLOCK_ID, copy.deepcopy(MANIFEST), snapshot(), duplicate)
        unknown_designator = dict(self.role_map)
        unknown_designator["R"] = "R99"
        with self.assertRaisesRegex(templates.BlockTemplateError, "not present in snapshot"):
            templates.extract_template(BLOCK_ID, copy.deepcopy(MANIFEST), snapshot(), unknown_designator)

    def test_manifest_errors_are_reported(self):
        manifest = copy.deepcopy(MANIFEST)
        manifest["internal_nets"].append(["PORT:ONLY"])
        with self.assertRaisesRegex(templates.BlockTemplateError, "no pin members"):
            templates.extract_template(BLOCK_ID, manifest, snapshot(), self.role_map)
        manifest = copy.deepcopy(MANIFEST)
        manifest["internal_nets"].append(["U.NOT_A_PIN"])
        with self.assertRaisesRegex(templates.BlockTemplateError, "no matching pin"):
            templates.extract_template(BLOCK_ID, manifest, snapshot(), self.role_map)

    def test_missing_snapshot_bbox_is_reported(self):
        components = base_components()
        for component in components:
            if component["ref"] == "C2":
                del component["bbox"]
        with self.assertRaisesRegex(templates.BlockTemplateError, "C2.+bbox"):
            templates.extract_template(
                BLOCK_ID, copy.deepcopy(MANIFEST), snapshot(components), self.role_map
            )


class InstantiateTemplateTests(TemplateFixture):
    NEW_ORIGIN = (1000, 2000)

    def test_pure_translation_of_parts_and_bboxes(self):
        template = self.template()
        applied = templates.instantiate_template(template, "page-1", self.NEW_ORIGIN)
        self.assertEqual(applied["page"], "page-1")
        parts = {part["role"]: part for part in applied["parts"]}
        self.assertEqual(parts["U"]["ref"], "U1")
        self.assertEqual((parts["U"]["x"], parts["U"]["y"]), (1000, 2000))
        self.assertEqual(parts["U"]["bbox"], {"minX": 970, "minY": 1970, "maxX": 1030, "maxY": 2030})
        self.assertEqual((parts["R"]["x"], parts["R"]["y"]), (1100, 1980))
        self.assertEqual((parts["C_A"]["x"], parts["C_A"]["y"]), (1060, 1980))
        self.assertEqual((parts["C_B"]["x"], parts["C_B"]["y"]), (1060, 2020))
        self.assertEqual(parts["C_A"]["rotation"], 90)
        self.assertEqual(
            applied["zone_union"],
            {"minX": 970, "minY": 1970, "maxX": 1110, "maxY": 2030},
        )

    def test_instantiate_at_snapshot_origin_reproduces_snapshot_geometry(self):
        template = self.template()
        applied = templates.instantiate_template(
            template, "p1", [template["origin"]["x"], template["origin"]["y"]]
        )
        by_ref = {part["ref"]: part for part in applied["parts"]}
        for component in base_components():
            expected = component["bbox"]
            self.assertEqual(by_ref[component["ref"]]["bbox"], expected, component["ref"])
            center = (
                (expected["minX"] + expected["maxX"]) / 2.0,
                (expected["minY"] + expected["maxY"]) / 2.0,
            )
            self.assertEqual((by_ref[component["ref"]]["x"], by_ref[component["ref"]]["y"]), center)

    def test_nets_are_copied_verbatim(self):
        applied = templates.instantiate_template(self.template(), "page-1", self.NEW_ORIGIN)
        self.assertEqual(
            applied["nets"],
            [
                {"name": "5V", "members": [["U1", "VDD"], ["C1", "1"]]},
                {"name": "GND", "members": [["U1", "GND"], ["C1", "2"], ["C2", "2"]]},
                {"name": BLOCK_ID + "_N3", "members": [["U1", "OUT"], ["C2", "1"]]},
                {"name": BLOCK_ID + "_N4", "members": [["U1", "IN"], ["R1", "2"]]},
                {"name": "DAC_L", "members": [["R1", "1"]]},
                {"name": "MODE_CFG", "members": [["U1", "MODE"]]},
            ],
        )

    def test_instantiation_is_deterministic_and_accepts_mapping_origin(self):
        template = self.template()
        first = templates.instantiate_template(template, "page-1", self.NEW_ORIGIN)
        second = templates.instantiate_template(template, "page-1", self.NEW_ORIGIN)
        third = templates.instantiate_template(
            template, "page-1", {"x": self.NEW_ORIGIN[0], "y": self.NEW_ORIGIN[1]}
        )
        self.assertEqual(first, second)
        self.assertEqual(first, third)

    def test_default_origin_role_is_first_manifest_role_without_u(self):
        manifest = {
            "id": BLOCK_ID,
            "parts": {
                "CAP_FIRST": {"part": "cap.22uf"},
                "CAP_SECOND": {"part": "cap.22uf"},
            },
        }
        # Net 1 can only hold together when CAP_FIRST=C1 / CAP_SECOND=C2;
        # net 2 (a legal single-member net) seals the remaining pin.
        manifest["internal_nets"] = [
            ["CAP_FIRST.1", "CAP_SECOND.2"],
            ["CAP_FIRST.2"],
        ]
        components = [
            comp("C1", "CAP-22U", (10, 10, 30, 30), [pin(1, "1", "N1"), pin(2, "2", "N3")]),
            comp("C2", "CAP-22U", (50, 10, 70, 30), [pin(1, "1", "N2"), pin(2, "2", "N1")]),
        ]
        role_map = role_resolver.resolve_roles(
            manifest, snapshot(components), resolved_parts_path=self.resolved_path
        )
        # Only CAP_FIRST=C1 keeps net 1 on a single snapshot net (N1).
        self.assertEqual(role_map, {"CAP_FIRST": "C1", "CAP_SECOND": "C2"})
        template = templates.extract_template(BLOCK_ID, manifest, snapshot(components), role_map)
        self.assertEqual(template["origin"]["role"], "CAP_FIRST")
        self.assertEqual(template["origin"]["ref"], "C1")
        applied = templates.instantiate_template(template, "p1", [0, 0])
        self.assertEqual(
            [part["ref"] for part in applied["parts"]], ["C1", "C2"]
        )

    def test_template_validation_errors(self):
        template = self.template()
        broken = copy.deepcopy(template)
        del broken["parts"][0]["bbox"]
        with self.assertRaisesRegex(templates.BlockTemplateError, "bbox"):
            templates.instantiate_template(broken, "p1", [0, 0])
        broken = copy.deepcopy(template)
        broken["parts"][0]["role"] = "Q"
        with self.assertRaisesRegex(templates.BlockTemplateError, "not in template.parts"):
            templates.instantiate_template(broken, "p1", [0, 0])
        broken = copy.deepcopy(template)
        broken["mystery"] = True
        with self.assertRaisesRegex(templates.BlockTemplateError, "unknown field"):
            templates.instantiate_template(broken, "p1", [0, 0])
        with self.assertRaisesRegex(templates.BlockTemplateError, "origin_xy"):
            templates.instantiate_template(template, "p1", "bad-origin")
        with self.assertRaisesRegex(templates.BlockTemplateError, "non-empty list"):
            templates.instantiate_template(
                {**template, "parts": []}, "p1", [0, 0]
            )
        with self.assertRaisesRegex(templates.BlockTemplateError, "schema"):
            templates.instantiate_template(
                {**template, "schema": "other/v1"}, "p1", [0, 0]
            )


if __name__ == "__main__":
    unittest.main()
