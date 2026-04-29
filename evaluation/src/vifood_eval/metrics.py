from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from .triples import triple_key


def retrieval_scores(
    retrieved: list[dict[str, Any]],
    gold: list[dict[str, Any]],
    k: int = 10,
) -> dict[str, float | int]:
    retrieved_keys = [triple_key(triple) for triple in retrieved[:k]]
    retrieved_set = {key for key in retrieved_keys if all(key)}
    gold_set = {triple_key(triple) for triple in gold if all(triple_key(triple))}
    hits = len(retrieved_set & gold_set)

    precision = hits / len(retrieved_set) if retrieved_set else 0.0
    recall = hits / len(gold_set) if gold_set else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    return {
        f"precision_at_{k}": precision,
        f"recall_at_{k}": recall,
        f"f1_at_{k}": f1,
        "retrieved_count": len(retrieved_set),
        "gold_count": len(gold_set),
        "hit_count": hits,
    }


def summarize_predictions(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    correct = sum(1 for row in rows if row.get("correct") is True)
    parsed = sum(1 for row in rows if str(row.get("parse_status", "")).startswith("ok"))
    by_qtype: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in rows:
        by_qtype[str(row.get("qtype_gold"))].append(row)

    return {
        "total": total,
        "correct": correct,
        "accuracy": correct / total if total else 0.0,
        "parse_failures": total - parsed,
        "parse_failure_rate": (total - parsed) / total if total else 0.0,
        "per_qtype": {
            qtype: {
                "total": len(qrows),
                "accuracy": sum(1 for row in qrows if row.get("correct") is True) / len(qrows),
            }
            for qtype, qrows in sorted(by_qtype.items())
        },
        "qtype_counts": dict(Counter(str(row.get("qtype_gold")) for row in rows)),
    }

