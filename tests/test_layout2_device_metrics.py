"""Tests for tools/layout2/device_metrics.py (easycirq-device-metrics/v1).

Offline only: the fixture is a fixed JSON document and the shipped asset is read
from ``easycirq/assets``. No EDA client, daemon or network is involved.

Covered: loader + validation (positive sizes, halo >= 0, field-path errors),
real measured values, halo expansion, unknown-part errors with a fix hint, and
measurement write-back (merge/update preserves provenance).
"""
import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / 'tools' / 'layout2' / 'device_metrics.py'
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location('layout2_device_metrics', MODULE_PATH)
dm = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = dm
_spec.loader.exec_module(dm)

ASSET_PATH = ROOT / 'easycirq' / 'assets' / 'device-metrics.json'


def fixture():
    """A small but complete metrics document used by most tests."""
    return {
        'schema': 'easycirq-device-metrics/v1',
        'measured_at': '2026-10-29',
        'source': {'client': 'EasyEDA Pro 4.1.78', 'method': 'fixture'},
        'parts': {
            'cap.100nf_0402': {
                'symbol': {'w': 21.0, 'h': 17.0},
                'pins': 2,
                'designator': {'size': 7, 'w': 7.7},
                'value': {'size': 7, 'w': 7.7},
                'halo': {'left': 22, 'right': 22, 'top': 16, 'bottom': 10},
                'provenance': 'symbol bbox measured 2026-10-29 (fixture)',
            },
            'ic.test_big': {
                'symbol': {'w': 100.0, 'h': 60.0},
                'pins': 24,
                'designator': {'size': 7, 'w': 8.5},
                'value': {'size': 7, 'w': 20.0},
                'halo': {'left': 5, 'right': 5, 'top': 2, 'bottom': 2},
                'measured_at': '2026-10-28',
                'provenance': 'fixture defaults pending measurement',
            },
        },
    }


def load_fixture_file():
    """Write the fixture to a temp file and load it through the public loader."""
    temp = tempfile.TemporaryDirectory()
    path = Path(temp.name) / 'device-metrics.json'
    path.write_text(json.dumps(fixture(), indent=1), encoding='utf-8')
    return temp, path


class ShippedAssetTests(unittest.TestCase):
    def setUp(self):
        self.metrics = dm.load()

    def test_default_path_is_the_shipped_asset(self):
        self.assertEqual(dm.DEFAULT_PATH, ASSET_PATH)
        self.assertEqual(Path(self.metrics.path), ASSET_PATH)

    def test_schema_and_part_count(self):
        self.assertEqual(self.metrics.schema, 'easycirq-device-metrics/v1')
        self.assertEqual(len(self.metrics), 25)
        self.assertEqual(self.metrics.measured_at, '2026-10-29')

    def test_measured_symbol_dimensions_are_real(self):
        expected = {
            'res.10k_0402': (21.0, 9.0),
            'cap.100nf_0402': (21.0, 17.0),
            'ic.es8311': (201.0, 121.0),
            'mcu.esp32s3_wroom1': (71.0, 421.0),
            'fb.120r_0603': (34.55, 5.28),
        }
        for part, (w, h) in expected.items():
            with self.subTest(part=part):
                entry = self.metrics.get(part)
                self.assertEqual(entry.symbol_w, w)
                self.assertEqual(entry.symbol_h, h)

    def test_unmeasured_fields_are_marked_pending(self):
        for part in self.metrics:
            with self.subTest(part=part):
                entry = self.metrics[part]
                # pins are explicitly null until the serial runner measures them
                self.assertIsNone(entry.pins)
                self.assertIn('pending measurement', entry.provenance)
                self.assertEqual(entry.designator_size, 7)
                self.assertEqual(entry.designator_w, 7.7)
                self.assertEqual(entry.value_size, 7)
                self.assertEqual(entry.value_w, 7.7)

    def test_part_measured_at_falls_back_to_document_date(self):
        self.assertEqual(self.metrics.get('ic.es8311').measured_at, '2026-10-29')

    def test_halo_is_available_for_every_part(self):
        for part in self.metrics:
            halo = self.metrics[part].halo
            self.assertGreaterEqual(halo.left + halo.right + halo.top + halo.bottom, 0)

    def test_unknown_part_raises_keyerror_with_hint(self):
        with self.assertRaises(KeyError) as caught:
            self.metrics.get('res.999k_0402')
        message = str(caught.exception)
        self.assertIn('res.999k_0402', message)
        self.assertIn('unknown device part', message)
        self.assertIn('measure_device_metrics.py', message)
        self.assertIn('cap.100nf_0402', message)

    def test_with_halo_unknown_part_raises_keyerror(self):
        with self.assertRaises(KeyError):
            self.metrics.with_halo({'minX': 0, 'minY': 0, 'maxX': 10, 'maxY': 10},
                                   'not.a.part')

    def test_dict_like_access(self):
        self.assertIn('ic.es8311', self.metrics)
        self.assertNotIn('ic.absent', self.metrics)
        self.assertEqual(set(self.metrics.keys()), {p.part for p in self.metrics.parts.values()})


class ValidationTests(unittest.TestCase):
    def assert_invalid(self, mutate, *expected_fragments):
        document = fixture()
        mutate(document)
        with self.assertRaises(dm.DeviceMetricsError) as caught:
            dm.validate(document)
        message = str(caught.exception)
        for fragment in expected_fragments:
            self.assertIn(fragment, message)

    def test_fixture_validates(self):
        metrics = dm.validate(fixture())
        self.assertEqual(len(metrics), 2)
        self.assertEqual(metrics.get('ic.test_big').pins, 24)

    def test_null_pins_means_unmeasured_and_is_valid(self):
        document = fixture()
        document['parts']['cap.100nf_0402']['pins'] = None
        self.assertIsNone(dm.validate(document).get('cap.100nf_0402').pins)

    def test_wrong_schema_rejected(self):
        def mutate(document):
            document['schema'] = 'easycirq-device-metrics/v2'
        self.assert_invalid(mutate, 'schema', 'easycirq-device-metrics/v1')

    def test_missing_schema_rejected(self):
        def mutate(document):
            del document['schema']
        self.assert_invalid(mutate, 'schema')

    def test_empty_parts_rejected(self):
        def mutate(document):
            document['parts'] = {}
        self.assert_invalid(mutate, 'parts', 'non-empty')

    def test_missing_part_field_rejected(self):
        def mutate(document):
            del document['parts']['cap.100nf_0402']['halo']
        self.assert_invalid(mutate, "parts['cap.100nf_0402'].halo", 'missing')

    def test_zero_symbol_width_rejected(self):
        def mutate(document):
            document['parts']['cap.100nf_0402']['symbol']['w'] = 0
        self.assert_invalid(mutate, 'symbol.w', '> 0')

    def test_negative_symbol_height_rejected(self):
        def mutate(document):
            document['parts']['ic.test_big']['symbol']['h'] = -1
        self.assert_invalid(mutate, 'symbol.h', 'must be > 0')

    def test_boolean_is_not_a_number(self):
        def mutate(document):
            document['parts']['ic.test_big']['symbol']['w'] = True
        self.assert_invalid(mutate, 'symbol.w', 'finite number')

    def test_negative_halo_rejected(self):
        def mutate(document):
            document['parts']['cap.100nf_0402']['halo']['left'] = -0.5
        self.assert_invalid(mutate, 'halo.left', '>= 0')

    def test_missing_halo_side_rejected(self):
        def mutate(document):
            del document['parts']['cap.100nf_0402']['halo']['bottom']
        self.assert_invalid(mutate, 'halo', 'bottom')

    def test_non_positive_designator_width_rejected(self):
        def mutate(document):
            document['parts']['ic.test_big']['designator']['w'] = 0
        self.assert_invalid(mutate, 'designator.w', '> 0')

    def test_empty_provenance_rejected(self):
        def mutate(document):
            document['parts']['ic.test_big']['provenance'] = '  '
        self.assert_invalid(mutate, 'provenance', 'non-empty string')

    def test_negative_pins_rejected(self):
        def mutate(document):
            document['parts']['ic.test_big']['pins'] = -2
        self.assert_invalid(mutate, 'pins', '>= 0')

    def test_fractional_pins_rejected(self):
        def mutate(document):
            document['parts']['ic.test_big']['pins'] = 2.5
        self.assert_invalid(mutate, 'pins', 'integer')

    def test_bad_measured_at_rejected(self):
        def mutate(document):
            document['measured_at'] = '29.10.2026'
        self.assert_invalid(mutate, 'measured_at', 'YYYY-MM-DD')

    def test_impossible_calendar_date_rejected(self):
        def mutate(document):
            document['parts']['ic.test_big']['measured_at'] = '2026-13-01'
        self.assert_invalid(mutate, 'measured_at', 'calendar date')

    def test_error_message_names_file(self):
        document = fixture()
        document['schema'] = 'bad'
        path = Path('some') / 'device-metrics.json'
        with self.assertRaises(dm.DeviceMetricsError) as caught:
            dm.validate(document, path=path)
        self.assertIn(str(path), str(caught.exception))

    def test_unknown_extra_keys_are_tolerated(self):
        document = fixture()
        document['future_field'] = {'note': 'added by a newer runner'}
        document['parts']['ic.test_big']['confidence'] = 'high'
        metrics = dm.validate(document)
        self.assertEqual(len(metrics), 2)


class WithHaloTests(unittest.TestCase):
    def setUp(self):
        self.metrics = dm.validate(fixture())
        self.bbox = {'minX': 100, 'minY': 200, 'maxX': 121, 'maxY': 217}

    def test_part_with_halo_expands_each_side(self):
        expanded = self.metrics.get('cap.100nf_0402').with_halo(self.bbox)
        self.assertEqual(expanded, {'minX': 78.0, 'minY': 184.0,
                                    'maxX': 143.0, 'maxY': 227.0})

    def test_metrics_with_halo_uses_part_lookup(self):
        expanded = self.metrics.with_halo(self.bbox, 'ic.test_big')
        self.assertEqual(expanded, {'minX': 95.0, 'minY': 198.0,
                                    'maxX': 126.0, 'maxY': 219.0})

    def test_sequence_bbox_keeps_its_shape(self):
        tuple_bbox = (100, 200, 121, 217)
        self.assertEqual(self.metrics.with_halo(tuple_bbox, 'cap.100nf_0402'),
                         (78.0, 184.0, 143.0, 227.0))
        self.assertEqual(self.metrics.with_halo(list(tuple_bbox), 'cap.100nf_0402'),
                         [78.0, 184.0, 143.0, 227.0])

    def test_explicit_halo_without_part_lookup(self):
        expanded = dm.with_halo(self.bbox, {'left': 1, 'right': 2, 'top': 3, 'bottom': 4})
        self.assertEqual(expanded, {'minX': 99.0, 'minY': 197.0,
                                    'maxX': 123.0, 'maxY': 221.0})

    def test_module_level_part_name_shorthand(self):
        halo = dm.get('cap.100nf_0402').halo
        expanded = dm.with_halo(self.bbox, 'cap.100nf_0402')
        self.assertEqual(expanded, {'minX': 100 - halo.left, 'minY': 200 - halo.top,
                                    'maxX': 121 + halo.right, 'maxY': 217 + halo.bottom})

    def test_module_level_get_reads_shipped_table(self):
        part = dm.get('res.10k_0402')
        self.assertEqual(part.symbol, {'w': 21.0, 'h': 9.0})
        self.assertEqual(part.with_halo(self.bbox)['minX'], 100 - part.halo.left)

    def test_zero_halo_is_identity(self):
        zero = dm.Halo()
        self.assertEqual(dm.with_halo(self.bbox, zero), self.bbox)

    def test_negative_halo_rejected(self):
        with self.assertRaises(dm.DeviceMetricsError):
            dm.with_halo(self.bbox, {'left': -1, 'right': 0, 'top': 0, 'bottom': 0})

    def test_missing_halo_side_rejected(self):
        with self.assertRaises(dm.DeviceMetricsError):
            dm.with_halo(self.bbox, {'left': 1, 'right': 1, 'top': 1})

    def test_missing_bbox_key_rejected(self):
        with self.assertRaises(dm.DeviceMetricsError):
            self.metrics.with_halo({'minX': 0, 'minY': 0, 'maxX': 10}, 'cap.100nf_0402')

    def test_wrong_bbox_length_rejected(self):
        with self.assertRaises(dm.DeviceMetricsError):
            dm.with_halo((0, 0, 10), {'left': 1, 'right': 1, 'top': 1, 'bottom': 1})

    def test_inverted_bbox_rejected(self):
        with self.assertRaises(dm.DeviceMetricsError):
            dm.with_halo({'minX': 10, 'minY': 0, 'maxX': 0, 'maxY': 10},
                         {'left': 1, 'right': 1, 'top': 1, 'bottom': 1})


class MergeAndSaveTests(unittest.TestCase):
    def setUp(self):
        self.document = fixture()
        self.part = 'cap.100nf_0402'
        self.before = copy.deepcopy(self.document)

    def test_merge_updates_supplied_fields_and_preserves_provenance(self):
        merged = dm.merge_part(self.document, self.part,
                               {'symbol': {'w': 30.0, 'h': 12.0}, 'pins': 2})
        entry = merged['parts'][self.part]
        self.assertEqual(entry['symbol'], {'w': 30.0, 'h': 12.0})
        self.assertEqual(entry['pins'], 2)
        # untouched halo/designator/value/provenance survive the update
        self.assertEqual(entry['halo'], {'left': 22, 'right': 22, 'top': 16, 'bottom': 10})
        self.assertEqual(entry['designator'], {'size': 7, 'w': 7.7})
        self.assertEqual(entry['provenance'], 'symbol bbox measured 2026-10-29 (fixture)')
        self.assertNotIn('measured_at', entry)

    def test_merge_does_not_mutate_the_input_document(self):
        dm.merge_part(self.document, self.part, {'symbol': {'w': 30.0}})
        self.assertEqual(self.document, self.before)

    def test_merge_new_measurement_records_provenance_and_date(self):
        merged = dm.merge_part(
            self.document, self.part,
            {'symbol': {'w': 21.0, 'h': 17.0}, 'pins': 2},
            measured_at='2026-10-30',
            provenance='re-measured 2026-10-30 (fixture runner)')
        entry = merged['parts'][self.part]
        self.assertEqual(entry['measured_at'], '2026-10-30')
        self.assertEqual(entry['provenance'], 're-measured 2026-10-30 (fixture runner)')
        # other parts keep their own provenance
        self.assertEqual(merged['parts']['ic.test_big']['provenance'],
                         'fixture defaults pending measurement')
        dm.validate(merged)

    def test_merge_nested_partial_halo_keeps_other_sides(self):
        merged = dm.merge_part(self.document, self.part, {'halo': {'left': 30}})
        self.assertEqual(merged['parts'][self.part]['halo'],
                         {'left': 30, 'right': 22, 'top': 16, 'bottom': 10})

    def test_merge_unknown_part_raises_keyerror(self):
        with self.assertRaises(KeyError) as caught:
            dm.merge_part(self.document, 'res.42_0402', {'symbol': {'w': 1, 'h': 1}})
        self.assertIn('unknown device part', str(caught.exception))

    def test_merge_can_add_a_new_part_when_allowed(self):
        new_part = {
            'symbol': {'w': 10.0, 'h': 4.0},
            'pins': 2,
            'designator': {'size': 7, 'w': 7.7},
            'value': {'size': 7, 'w': 7.7},
            'halo': {'left': 22, 'right': 22, 'top': 16, 'bottom': 10},
            'provenance': 'measured 2026-10-30 (fixture runner)',
        }
        merged = dm.merge_part(self.document, 'res.42_0402', new_part,
                               measured_at='2026-10-30', allow_new=True)
        self.assertIn('res.42_0402', merged['parts'])
        dm.validate(merged)

    def test_merge_new_part_without_required_fields_is_rejected(self):
        with self.assertRaises(dm.DeviceMetricsError):
            dm.merge_part(self.document, 'res.42_0402', {'symbol': {'w': 1, 'h': 1}},
                          allow_new=True)

    def test_merge_invalid_value_is_rejected_by_validation(self):
        with self.assertRaises(dm.DeviceMetricsError):
            dm.merge_part(self.document, self.part, {'symbol': {'w': -3}})

    def test_save_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / 'device-metrics.json'
            written = dm.save(self.document, target)
            self.assertEqual(written, target)
            text = target.read_text(encoding='utf-8')
            self.assertTrue(text.endswith('\n'))
            self.assertIn('\n "parts": {', text)  # asset style: one-space indent
            loaded = dm.load(target)
            self.assertEqual(len(loaded), 2)
            self.assertEqual(loaded.get(self.part).halo, dm.Halo(22, 22, 16, 10))
            self.assertEqual(loaded.get('ic.test_big').measured_at, '2026-10-28')

    def test_save_rejects_invalid_document_without_writing(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / 'device-metrics.json'
            self.document['parts'][self.part]['halo']['top'] = -1
            with self.assertRaises(dm.DeviceMetricsError):
                dm.save(self.document, target)
            self.assertFalse(target.exists())


class FixtureJsonTests(unittest.TestCase):
    def test_fixture_json_loads_through_public_api(self):
        temp, path = load_fixture_file()
        try:
            metrics = dm.load(path)
            self.assertEqual(metrics.path, path)
            self.assertEqual(metrics.get('cap.100nf_0402').pins, 2)
            expanded = metrics.get('cap.100nf_0402').with_halo(
                {'minX': 100, 'minY': 200, 'maxX': 121, 'maxY': 217})
            self.assertEqual(expanded, {'minX': 78.0, 'minY': 184.0,
                                        'maxX': 143.0, 'maxY': 227.0})
            self.assertEqual(metrics.with_halo((100, 200, 121, 217), 'ic.test_big'),
                             (95.0, 198.0, 126.0, 219.0))
        finally:
            temp.cleanup()

    def test_missing_file_raises_readable_error(self):
        with self.assertRaises(dm.DeviceMetricsError) as caught:
            dm.load(Path(tempfile.gettempdir()) / 'definitely-missing-device-metrics.json')
        self.assertIn('cannot read device metrics', str(caught.exception))

    def test_invalid_json_raises_readable_error(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'device-metrics.json'
            path.write_text('{"schema": ', encoding='utf-8')
            with self.assertRaises(dm.DeviceMetricsError) as caught:
                dm.load(path)
            self.assertIn('invalid JSON', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
