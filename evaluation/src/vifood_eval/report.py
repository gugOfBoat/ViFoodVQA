from __future__ import annotations

import argparse
import csv
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any

from .metrics import summarize_predictions


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize ViFoodVQA evaluation outputs.")
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    rows = _load_prediction_rows(run_dir)
    if not rows:
        raise RuntimeError(f"No prediction rows found under {run_dir}")

    summary_rows = _summary_rows(rows)
    _write_csv(run_dir / "metrics_overall.csv", summary_rows)
    _write_csv(run_dir / "metrics_per_qtype.csv", _per_qtype_rows(rows))
    retrieval_rows = _retrieval_rows(rows)
    if retrieval_rows:
        _write_csv(run_dir / "metrics_retrieval.csv", retrieval_rows)
    _write_markdown(run_dir / "metrics_summary.md", summary_rows)
    _write_error_subset(run_dir, rows)
    print(f"Wrote metrics to {run_dir}")


def _load_prediction_rows(run_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted((run_dir / "predictions").glob("*.jsonl")):
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
    return rows


def _summary_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["model"]), str(row["condition"]))].append(row)

    result = []
    for (model, condition), group in sorted(grouped.items()):
        summary = summarize_predictions(group)
        result.append(
            {
                "model": model,
                "condition": condition,
                "total": summary["total"],
                "accuracy": round(summary["accuracy"], 6),
                "parse_failure_rate": round(summary["parse_failure_rate"], 6),
                "qtype_classifier_accuracy": _classifier_accuracy(group),
            }
        )
    return result


def _per_qtype_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["model"]), str(row["condition"]), str(row.get("qtype_gold")))].append(row)

    result = []
    for (model, condition, qtype), group in sorted(grouped.items()):
        total = len(group)
        correct = sum(1 for row in group if row.get("correct") is True)
        result.append(
            {
                "model": model,
                "condition": condition,
                "qtype": qtype,
                "total": total,
                "accuracy": round(correct / total if total else 0.0, 6),
            }
        )
    return result


def _retrieval_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if "precision_at_10" in row:
            grouped[(str(row["model"]), str(row["condition"]))].append(row)

    result = []
    for (model, condition), group in sorted(grouped.items()):
        result.append(
            {
                "model": model,
                "condition": condition,
                "total": len(group),
                "precision_at_10": round(_mean(group, "precision_at_10"), 6),
                "recall_at_10": round(_mean(group, "recall_at_10"), 6),
                "f1_at_10": round(_mean(group, "f1_at_10"), 6),
            }
        )
    return result


def _classifier_accuracy(rows: list[dict[str, Any]]) -> float | str:
    classified = [row for row in rows if row.get("qtype_pred")]
    if not classified:
        return ""
    correct = sum(1 for row in classified if row.get("qtype_pred") == row.get("qtype_gold"))
    return round(correct / len(classified), 6)


def _mean(rows: list[dict[str, Any]], key: str) -> float:
    values = [float(row[key]) for row in rows if key in row]
    return sum(values) / len(values) if values else 0.0


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_markdown(path: Path, rows: list[dict[str, Any]]) -> None:
    lines = [
        "# ViFoodVQA Evaluation Summary",
        "",
        "| Model | Condition | Total | Accuracy | Parse failure rate |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            f"| {row['model']} | {row['condition']} | {row['total']} | "
            f"{row['accuracy']:.4f} | {row['parse_failure_rate']:.4f} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_error_subset(run_dir: Path, rows: list[dict[str, Any]], size: int = 120) -> None:
    by_qtype: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_qtype[str(row.get("qtype_gold"))].append(row)

    rng = random.Random(42)
    selected: list[dict[str, Any]] = []
    per_group = max(1, size // max(1, len(by_qtype)))
    for group in by_qtype.values():
        selected.extend(rng.sample(group, min(per_group, len(group))))
    selected = selected[:size]

    path = run_dir / "human_error_subset.csv"
    fields = [
        "model",
        "condition",
        "vqa_id",
        "image_id",
        "question",
        "qtype_gold",
        "answer_gold",
        "answer_pred",
        "correct",
        "error_cause",
        "notes",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in selected:
            writer.writerow({field: row.get(field, "") for field in fields})


if __name__ == "__main__":
    main()
