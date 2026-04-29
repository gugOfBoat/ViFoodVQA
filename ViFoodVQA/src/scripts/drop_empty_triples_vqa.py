from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from collect_ground_truth_stats import (
    DEFAULT_SUPABASE_ENV,
    PAGE_SIZE,
    make_supabase_client,
    normalize_split,
    require_supabase_config,
)


BATCH_SIZE = 100


def fetch_vqa_rows(client: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = 0

    while True:
        response = (
            client.table("vqa")
            .select("vqa_id,image_id,qtype,split,is_checked,is_drop,verify_decision,triples_used")
            .order("vqa_id")
            .range(start, start + PAGE_SIZE - 1)
            .execute()
        )
        batch = response.data or []
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        start += PAGE_SIZE

    return rows


def parse_triples_used_list(value: Any) -> list[Any] | None:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, list):
            return parsed
    return None


def has_empty_triples_used_list(row: dict[str, Any]) -> bool:
    triples_used = parse_triples_used_list(row.get("triples_used"))
    return isinstance(triples_used, list) and len(triples_used) == 0


def find_affected_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if row.get("is_drop") is False and has_empty_triples_used_list(row)
    ]


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "affected_count": len(rows),
        "split_counts": dict(sorted(Counter(normalize_split(row.get("split")) for row in rows).items())),
        "qtype_counts": dict(sorted(Counter((row.get("qtype") or "<empty>") for row in rows).items())),
        "is_checked_counts": dict(sorted(Counter(str(row.get("is_checked")) for row in rows).items())),
        "verify_decision_counts": dict(
            sorted(Counter((row.get("verify_decision") or "<null>") for row in rows).items())
        ),
        "unique_image_ids": len({row.get("image_id") for row in rows if row.get("image_id")}),
        "vqa_ids": [row["vqa_id"] for row in rows if row.get("vqa_id") is not None],
    }


def chunks(items: list[int], size: int) -> list[list[int]]:
    return [items[index:index + size] for index in range(0, len(items), size)]


def apply_drop(client: Any, rows: list[dict[str, Any]], batch_size: int) -> int:
    vqa_ids = [int(row["vqa_id"]) for row in rows if row.get("vqa_id") is not None]
    if not vqa_ids:
        return 0

    updated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    updated = 0
    for batch_ids in chunks(vqa_ids, batch_size):
        response = (
            client.table("vqa")
            .update({"is_drop": True, "updated_at": updated_at})
            .in_("vqa_id", batch_ids)
            .eq("is_drop", False)
            .execute()
        )
        updated += len(response.data or batch_ids)
        print(f"Updated {min(updated, len(vqa_ids))}/{len(vqa_ids)} rows...", flush=True)

    return min(updated, len(vqa_ids))


def print_summary(summary: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    print("Empty-triples VQA cleanup")
    print(f"Affected rows: {summary['affected_count']}")
    print(f"Unique image IDs: {summary['unique_image_ids']}")
    print(f"Split counts: {summary['split_counts']}")
    print(f"QType counts: {summary['qtype_counts']}")
    print(f"is_checked counts: {summary['is_checked_counts']}")
    print(f"verify_decision counts: {summary['verify_decision_counts']}")
    print(f"First 50 affected vqa_id values: {summary['vqa_ids'][:50]}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mark Supabase VQA rows with empty triples_used as dropped."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply updates. Default is dry-run only.",
    )
    parser.add_argument(
        "--env",
        type=Path,
        default=DEFAULT_SUPABASE_ENV,
        help=f"Supabase .env path. Default: {DEFAULT_SUPABASE_ENV}",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=BATCH_SIZE,
        help=f"Supabase update batch size. Default: {BATCH_SIZE}.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print summary as JSON.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = require_supabase_config(args.env)
    client = make_supabase_client(config)

    rows = fetch_vqa_rows(client)
    affected_rows = find_affected_rows(rows)
    summary = summarize(affected_rows)
    summary["mode"] = "apply" if args.apply else "dry-run"

    print_summary(summary, as_json=args.json)

    if not args.apply:
        if not args.json:
            print("Dry-run only. Pass --apply to set is_drop=true for affected rows.")
        return 0

    updated = apply_drop(client, affected_rows, args.batch_size)
    print(f"Applied cleanup. Updated rows: {updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
