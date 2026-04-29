from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vifood_eval.data import VQASample, load_split, validate_samples


def temp_dir() -> TemporaryDirectory[str]:
    root = Path(os.environ.get("VIFOOD_EVAL_TEST_TMP", "C:/tmp"))
    root.mkdir(parents=True, exist_ok=True)
    return TemporaryDirectory(dir=root)


class DataTests(unittest.TestCase):
    def test_load_split_validates_images_and_fields(self) -> None:
        with temp_dir() as tmp:
            root = Path(tmp)
            (root / "data").mkdir()
            (root / "images").mkdir()
            (root / "images" / "x.jpg").write_bytes(b"fake")
            row = {
                "vqa_id": 1,
                "image_id": "image1",
                "image": "images/x.jpg",
                "qtype": "ingredients",
                "question": "Q?",
                "choices": {"A": "a", "B": "b", "C": "c", "D": "d"},
                "answer": "A",
                "triples_used": [{"subject": "s", "relation": "r", "target": "t"}],
            }
            (root / "data" / "test.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")

            samples = load_split(root, "test")

            self.assertEqual(samples[0].vqa_id, 1)
            self.assertEqual(samples[0].image_path, root / "images" / "x.jpg")

    def test_validate_rejects_missing_image(self) -> None:
        sample = VQASample(
            row={
                "vqa_id": 1,
                "image_id": "image1",
                "image": "images/missing.jpg",
                "qtype": "ingredients",
                "question": "Q?",
                "choices": {"A": "a", "B": "b", "C": "c", "D": "d"},
                "answer": "A",
                "triples_used": [{"subject": "s", "relation": "r", "target": "t"}],
            },
            split="test",
            data_dir=Path("missing-root"),
        )
        with self.assertRaises(FileNotFoundError):
            validate_samples([sample])

    def test_load_split_supports_huggingface_parquet(self) -> None:
        import pyarrow as pa
        import pyarrow.parquet as pq

        with temp_dir() as tmp:
            root = Path(tmp)
            (root / "data").mkdir()
            (root / "images").mkdir()
            (root / "images" / "image1.jpg").write_bytes(b"fake")
            table = pa.Table.from_pylist(
                [
                    {
                        "vqa_id": 1,
                        "image_id": "image1",
                        "image": {"path": "image1.jpg", "bytes": None},
                        "qtype": "ingredients",
                        "question": "Q?",
                        "choices": {"A": "a", "B": "b", "C": "c", "D": "d"},
                        "answer": "A",
                        "rationale": "R",
                        "triples_used": [
                            {"subject": "s", "relation": "r", "target": "t"}
                        ],
                    }
                ]
            )
            pq.write_table(table, root / "data" / "test-00000-of-00001.parquet")

            samples = load_split(root, "test")

            self.assertEqual(samples[0].row["image"], "images/image1.jpg")
            self.assertEqual(samples[0].image_path, root / "images" / "image1.jpg")


if __name__ == "__main__":
    unittest.main()
