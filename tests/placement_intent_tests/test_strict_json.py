"""Strict JSON parsing: duplicate keys, NaN/Infinity, BOM, garbage.

Raw text (not ``json.dumps``) is used wherever the bytes themselves matter.
"""
import unittest

from . import fixtures, support


def valid_text():
    return fixtures.json_text(fixtures.small_case())


class DuplicateKeyTests(support.CliTestCase):
    def test_duplicate_top_level_key_is_rejected(self):
        text = valid_text()
        self.assertTrue(text.startswith("{\n"))
        duplicate = ('{\n  "schema": "%s",\n' % fixtures.SCHEMA_INPUT
                     + text[2:])
        path = self.write_raw_input("duplicate.json", duplicate)
        result = self.run_on("validate", path)
        self.assert_invalid(result, "json_duplicate_key")

    def test_duplicate_nested_key_is_rejected(self):
        text = valid_text().replace(
            '"instance_id": "cmp:A",',
            '"instance_id": "cmp:A",\n      "instance_id": "cmp:A",',
            1)
        path = self.write_raw_input("duplicate-nested.json", text)
        result = self.run_on("validate", path)
        self.assert_invalid(result, "json_duplicate_key")


class NonFiniteNumberTests(support.CliTestCase):
    def test_nan_literal_is_rejected(self):
        text = valid_text().replace('"dx_mm": 0.0', '"dx_mm": NaN', 1)
        path = self.write_raw_input("nan.json", text)
        result = self.run_on("validate", path)
        self.assert_invalid(result, "json_invalid")

    def test_positive_infinity_literal_is_rejected(self):
        text = valid_text().replace('"weight": 1.0',
                                    '"weight": Infinity', 1)
        path = self.write_raw_input("infinity.json", text)
        result = self.run_on("validate", path)
        self.assert_invalid(result, "json_invalid")

    def test_negative_infinity_literal_is_rejected(self):
        text = valid_text().replace('"weight": 1.0',
                                    '"weight": -Infinity', 1)
        path = self.write_raw_input("negative-infinity.json", text)
        result = self.run_on("validate", path)
        self.assert_invalid(result, "json_invalid")

    def test_nan_in_size_is_rejected(self):
        text = valid_text().replace('"w": 4.0', '"w": NaN', 1)
        path = self.write_raw_input("nan-size.json", text)
        result = self.run_on("validate", path)
        self.assert_invalid(result, "json_invalid")


class JsonShapeTests(support.CliTestCase):
    def test_non_object_root_array(self):
        path = self.write_raw_input("array.json", "[]")
        result = self.run_on("validate", path)
        self.assert_invalid(result, "json_invalid")

    def test_non_object_root_number(self):
        path = self.write_raw_input("number.json", "42")
        result = self.run_on("validate", path)
        self.assert_invalid(result, "json_invalid")

    def test_trailing_content_after_object(self):
        path = self.write_raw_input("trailing.json",
                                    valid_text() + "  \"extra\"\n",
                                    newline=True)
        result = self.run_on("validate", path)
        self.assert_invalid(result, "json_invalid")

    def test_empty_file(self):
        path = self.write_raw_input("empty.json", "")
        result = self.run_on("validate", path)
        self.assert_invalid(result, "json_invalid")

    def test_invalid_utf8_bytes(self):
        path = self.write_bytes_input(
            "bad-utf8.json", b'{"schema": "\xff\xfe"}')
        result = self.run_on("validate", path)
        self.assert_invalid(result, "json_invalid")


class Utf8BomTests(support.CliTestCase):
    def test_utf8_bom_is_accepted(self):
        text = valid_text()
        path = self.write_bytes_input(
            "bom.json", b"\xef\xbb\xbf" + text.encode("utf-8"))
        result = self.run_on("validate", path)
        self.assert_exit_status(result, 0, "valid")
        payload = self.payload(result)
        self.assertIs(payload.get("valid"), True)
        # The recorded hash/bytes are of the raw file including the BOM.
        self.assertEqual(payload["input"]["sha256"],
                         support.sha256_file(path))
        self.assertEqual(payload["input"]["bytes"], path.stat().st_size)


if __name__ == "__main__":
    unittest.main()
