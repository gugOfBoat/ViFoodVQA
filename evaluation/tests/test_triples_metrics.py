from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vifood_eval.metrics import retrieval_scores
from vifood_eval.triples import expand_path_row, expand_path_rows, slug


class TripleMetricTests(unittest.TestCase):
    def test_expand_two_hop_ingredient_path(self) -> None:
        row = {
            "subject": "Pho Bo",
            "relation": "ingredientCategory",
            "target": "Thit",
            "via": "Thit Bo",
        }
        self.assertEqual(
            expand_path_row(row),
            [
                {"subject": "Pho Bo", "relation": "hasIngredient", "target": "Thit Bo"},
                {"subject": "Thit Bo", "relation": "ingredientCategory", "target": "Thit"},
            ],
        )

    def test_expand_path_rows_dedupes_and_limits(self) -> None:
        rows = [
            {"subject": "A", "relation": "r", "target": "B", "via": None},
            {"subject": "A", "relation": "r", "target": "B", "via": None},
            {"subject": "B", "relation": "r2", "target": "C", "via": None},
        ]
        self.assertEqual(len(expand_path_rows(rows, limit=10)), 2)

    def test_retrieval_scores_at_10(self) -> None:
        retrieved = [
            {"subject": "A", "relation": "r", "target": "B"},
            {"subject": "X", "relation": "r", "target": "Y"},
        ]
        gold = [{"subject": "A", "relation": "r", "target": "B"}]
        scores = retrieval_scores(retrieved, gold, k=10)
        self.assertEqual(scores["hit_count"], 1)
        self.assertEqual(scores["precision_at_10"], 0.5)
        self.assertEqual(scores["recall_at_10"], 1.0)

    def test_slug_removes_vietnamese_accents(self) -> None:
        self.assertEqual(slug("Phở Bò"), "pho-bo")


if __name__ == "__main__":
    unittest.main()

