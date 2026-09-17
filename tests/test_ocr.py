import unittest

from bilan_extractor.discovery import normalized_text, page_anchor_matches
from bilan_extractor.coordinates import normalize_ocr_bbox
from bilan_extractor.fiscal_period import fiscal_end_from_text, header_date
from bilan_extractor.ocr import Box, NUMBER_RE, OcrLine, box_from_polygon, parse_number
from bilan_extractor.table_geometry import labelled_rows, merge_numeric_fragments
from bilan_extractor.units import document_unit
from bilan_extractor.selection import select_current_value


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

    def test_row_values_are_assigned_to_stable_x_columns(self):
        lines = [
            OcrLine("au 30/06/20", Box(1176, 790, 1316, 821), 0.99),
            OcrLine("au 30/06/19", Box(1490, 790, 1631, 821), 0.99),
            OcrLine("Total général actif", Box(618, 918, 889, 942), 0.99),
            OcrLine("3 794 380", Box(1224, 915, 1347, 944), 0.99),
            OcrLine("4 262 139", Box(1500, 915, 1645, 944), 0.99),
            OcrLine("80 820", Box(1260, 960, 1347, 989), 0.99),
            OcrLine("63 315", Box(1550, 960, 1645, 989), 0.99),
        ]
        rows = labelled_rows(lines, [Box(596, 535, 2108, 2508)])
        self.assertEqual(len(rows), 1)
        values = rows[0]["values"]
        self.assertEqual([value["column_index"] for value in values], [0, 1])
        self.assertEqual([value["column_header"] for value in values], ["au 30/06/20", "au 30/06/19"])

    def test_fiscal_period_and_header_date_are_parsed(self):
        self.assertEqual(str(fiscal_end_from_text("Exercice clos le 31 août 2021")), "2021-08-31")
        self.assertEqual(str(fiscal_end_from_text("Exercice clos le 30/06/2020")), "2020-06-30")
        self.assertEqual(str(header_date("au 30/06/20")), "2020-06-30")

    def test_ocr_pixels_are_normalized_using_pdf_points_and_300_dpi(self):
        self.assertEqual(
            normalize_ocr_bbox([250, 500, 500, 1000], page_width_pt=600, page_height_pt=800),
            [0.1, 0.15, 0.2, 0.3],
        )

    def test_document_unit_prefers_explicit_thousands_over_euro_mentions(self):
        lines = [
            OcrLine("Montants exprimés en euros", Box(0, 0, 1, 1), 1),
            OcrLine("Les comptes sont en milliers d'euros", Box(0, 2, 1, 3), 1),
        ]
        self.assertEqual(document_unit(lines)[0], "kEUR")

    def test_adjacent_ocr_fragments_become_one_financial_cell(self):
        fragments = [
            OcrLine("367", Box(1426, 2791, 1507, 2831), 0.99),
            OcrLine("608", Box(1514, 2791, 1593, 2831), 0.99),
            OcrLine("367", Box(2187, 2791, 2268, 2831), 0.99),
            OcrLine("608", Box(2274, 2791, 2353, 2831), 0.99),
        ]
        cells = merge_numeric_fragments(fragments)
        self.assertEqual([cell.text for cell in cells], ["367 608", "367 608"])
        self.assertEqual((cells[0].box.x0, cells[0].box.x1), (1426, 1593))

    def test_explicit_exercice_n_header_selects_current_value_without_a_date(self):
        row = {
            "field_key": "BS_CASH_CURRENT_ASSET_FRGAAP",
            "label_text": "Disponibilités",
            "page": 2,
            "values": [
                {"parsed_value": 367608, "bbox_px": [1, 2, 3, 4], "column_header": None},
                {"parsed_value": 367608, "bbox_px": [5, 6, 7, 8], "column_header": "Exercice N clos le"},
            ],
        }
        selected = select_current_value(row, None)
        self.assertEqual(selected["value"], 367608)
        self.assertEqual(selected["confidence"], 0.92)
