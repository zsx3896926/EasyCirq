"""Import smoke test: the bootstrap must expose the implementation package."""
from __future__ import annotations

import unittest

from . import load

canonical = load('canonical')


class ImportTest(unittest.TestCase):
    def test_sha256_matches_known_vector(self):
        self.assertEqual(
            canonical.sha256_text('abc'),
            'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')

    def test_bool_is_not_a_number(self):
        with self.assertRaises(Exception):
            canonical.number(True, where='x')

    def test_nan_is_rejected(self):
        with self.assertRaises(Exception):
            canonical.number(float('nan'), where='x')


if __name__ == '__main__':
    unittest.main()
