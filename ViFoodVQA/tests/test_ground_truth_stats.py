from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "src" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from collect_ground_truth_stats import compute_vqa_stats, normalize_split, should_count_vqa_row


class GroundTruthStatsPolicyTest(unittest.TestCase):
    def test_normalize_split_aliases(self) -> None:
        self.assertEqual(normalize_split("train"), "train")
        self.assertEqual(normalize_split("training"), "train")
        self.assertEqual(normalize_split("validate"), "validation")
        self.assertEqual(normalize_split("val"), "validation")
        self.assertEqual(normalize_split("dev"), "validation")
        self.assertEqual(normalize_split("testing"), "test")
        self.assertEqual(normalize_split("custom"), "custom")
        self.assertEqual(normalize_split(None), "<empty>")

    def test_vqa_policy_only_filters_test_rows(self) -> None:
        self.assertTrue(
            should_count_vqa_row(
                {"split": "train", "is_checked": False, "is_drop": True}
            )
        )
        self.assertTrue(
            should_count_vqa_row(
                {"split": "validate", "is_checked": False, "is_drop": True}
            )
        )
        self.assertTrue(
            should_count_vqa_row(
                {
                    "split": "test",
                    "is_checked": True,
                    "is_drop": False,
                    "verify_decision": "DROP",
                }
            )
        )
        self.assertFalse(
            should_count_vqa_row(
                {"split": "test", "is_checked": False, "is_drop": False}
            )
        )
        self.assertFalse(
            should_count_vqa_row(
                {"split": "test", "is_checked": True, "is_drop": True}
            )
        )
        self.assertFalse(
            should_count_vqa_row(
                {"split": "unknown", "is_checked": True, "is_drop": False}
            )
        )

    def test_compute_vqa_stats_uses_canonical_policy(self) -> None:
        rows = [
            {
                "vqa_id": 1,
                "image_id": "img1",
                "qtype": "ingredients",
                "split": "train",
                "is_checked": False,
                "is_drop": True,
                "triples_used": [],
            },
            {
                "vqa_id": 2,
                "image_id": "img2",
                "qtype": "origin_locality",
                "split": "validate",
                "is_checked": False,
                "is_drop": True,
                "triples_used": '[{"subject":"a","relation":"b","target":"c"}]',
            },
            {
                "vqa_id": 3,
                "image_id": "img3",
                "qtype": "ingredients",
                "split": "test",
                "is_checked": True,
                "is_drop": False,
                "verify_decision": "DROP",
                "triples_used": [{"subject": "a", "relation": "b", "target": "c"}],
            },
            {
                "vqa_id": 4,
                "image_id": "img4",
                "qtype": "ingredients",
                "split": "test",
                "is_checked": True,
                "is_drop": True,
                "verify_decision": "KEEP",
                "triples_used": [],
            },
            {
                "vqa_id": 5,
                "image_id": "img5",
                "qtype": "ingredients",
                "split": "unknown",
                "is_checked": True,
                "is_drop": False,
                "triples_used": [],
            },
        ]

        stats = compute_vqa_stats(rows)

        self.assertEqual(stats["canonical_total"], 3)
        self.assertEqual(
            stats["canonical_split_counts"],
            {"train": 1, "validation": 1, "test": 1},
        )
        self.assertEqual(stats["canonical_unique_image_ids"], 3)
        self.assertEqual(stats["canonical_empty_triples_used"], 1)
        self.assertEqual(
            stats["canonical_qtype_distribution"],
            {"ingredients": 2, "origin_locality": 1},
        )
        self.assertEqual(stats["raw_split_counts"]["unknown"], 1)
        self.assertEqual(stats["unknown_split_counts"], {"unknown": 1})
        self.assertEqual(stats["counted_test_verify_decision_distribution"], {"DROP": 1})


if __name__ == "__main__":
    unittest.main()
