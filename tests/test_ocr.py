import unittest

from bilan_extractor.discovery import normalized_text, page_anchor_matches
from bilan_extractor.ocr import Box, NUMBER_RE, OcrLine, box_from_polygon, parse_number


class OcrParsingTest(unittest.TestCase):
    def test_polygon_becomes_axis_aligned_box(self):
        box = box_from_polygon([[12, 25], [40, 20], [42, 55], [10, 52]])
        self.assertEqual((box.x0, box.y0, box.x1, box.y1), (10, 20, 42, 55))

    def test_parse_french_thousands_and_negative_numbers(self):
        self.assertEqual(parse_number("1 250 000"), 1250000)
        self.assertEqual(parse_number("1.250.000"), 1250000)
        self.assertEqual(parse_number("-97 957"), -97957)
        self.assertEqual(parse_number("12,5"), 12.5)

    def test_number_regex_does_not_split_grouped_number(self):
        self.assertEqual(
            NUMBER_RE.findall("Achats 1 182 000 et variation -97 957"),
            ["1 182 000", "-97 957"],
        )

    def test_page_discovery_is_accent_insensitive(self):
        lines = [
            OcrLine("Compte de Résultat", Box(0, 0, 10, 10), 0.99),
            OcrLine("Impôts sur les bénéfices", Box(0, 20, 10, 30), 0.99),
        ]
        matches = page_anchor_matches(lines)
        self.assertEqual(normalized_text("Résultat"), "resultat")
        self.assertEqual(len(matches["income_statement"]), 2)
