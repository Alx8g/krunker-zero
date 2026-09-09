"""Hand-written specification checks for the byte-level differential oracle."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from test_query_differential import reference, vectors


class QueryReferenceTests(unittest.TestCase):
    def test_duplicates_blanks_and_plus(self):
        self.assertEqual(reference('?a=1&a=2&empty&x=a+b')[0], 'a=1&a=2&empty=&x=a+b')

    def test_utf8_and_invalid_bytes_together(self):
        self.assertEqual(reference('x=%b0🎮?%\ufeff')[0], 'x=%EF%BF%BD%F0%9F%8E%AE%3F%25%EF%BB%BF')

    def test_unpaired_surrogates_are_replacement_characters(self):
        self.assertEqual(reference('x=\ud800')[0], 'x=%EF%BF%BD')

    def test_paired_surrogates_are_one_codepoint(self):
        self.assertEqual(reference('x=\ud83c\udfae')[0], 'x=%F0%9F%8E%AE')

    def test_utf16_key_order(self):
        self.assertEqual(reference('\ue000=a&\U00010000=b')[1], 'probe=%21%7E&%F0%90%80%80=b&%EE%80%80=a')

    def test_seed_and_prefix_are_deterministic(self):
        self.assertEqual(vectors(300,1), vectors(300,1))
        self.assertNotEqual(vectors(300,1), vectors(300,2))
        self.assertEqual(vectors(256,1)[-1], 'x=%FF')


if __name__=='__main__':unittest.main()
