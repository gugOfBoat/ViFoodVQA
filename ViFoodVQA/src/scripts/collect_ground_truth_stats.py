from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import dotenv_values


SCRIPT_DIR = Path(__file__).resolve().parent
VQA_ROOT = SCRIPT_DIR.parents[1]
REPO_ROOT = VQA_ROOT.parent
KG_ROOT = REPO_ROOT / "ViFoodKG"

DEFAULT_SUPABASE_ENV = VQA_ROOT / ".env"
DEFAULT_NEO4J_ENV = KG_ROOT / ".env"
DEFAULT_NEO4J_FALLBACK_ENV = VQA_ROOT / ".env"

PAGE_SIZE = 1000
CANONICAL_SPLITS = ("train", "validation", "test")
VALIDATION_ALIASES = {"val", "valid", "validate", "validation", "dev"}
LLM_SOURCE_VALUES = {"Cognitive_Reasoning", "Common_Sense", "LLM_Knowledge"}


@dataclass(frozen=True)
class SupabaseConfig:
    url: str
    key: str


@dataclass(frozen=True)
class Neo4jConfig:
    uri: str
    username: str
    password: str
    database: str | None = None


def norm_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def normalize_split(value: Any) -> str:
    split = norm_text(value).lower().replace("-", "_")
    if split in {"train", "training"}:
        return "train"
    if split in VALIDATION_ALIASES:
        return "validation"
    if split in {"test", "testing"}:
        return "test"
    return split or "<empty>"


def parse_jsonish(value: Any) -> Any:
    if value is None:
        return []
    if isinstance(value, (list, dict)):
        return value
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return []
    return []


def has_nonempty_triples_used(row: dict[str, Any]) -> bool:
    triples_used = parse_jsonish(row.get("triples_used"))
    return isinstance(triples_used, list) and len(triples_used) > 0


def should_count_vqa_row(row: dict[str, Any]) -> bool:
    """Canonical count policy for Supabase VQA rows."""
    if row.get("is_drop") is True:
        return False
    if not has_nonempty_triples_used(row):
        return False

    split = normalize_split(row.get("split"))
    if split == "test":
        return row.get("is_checked") is True
    if split in {"train", "validation"}:
        return True
    return False


def sorted_counter(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}


def load_env_values(primary_env: Path, fallback_env: Path | None = None) -> dict[str, str]:
    values: dict[str, str] = {}
    if fallback_env and fallback_env.exists():
        values.update({k: v for k, v in dotenv_values(fallback_env).items() if v is not None})
    if primary_env.exists():
        values.update({k: v for k, v in dotenv_values(primary_env).items() if v is not None})
    values.update({k: v for k, v in os.environ.items() if v is not None})
    return values


def require_supabase_config(env_path: Path) -> SupabaseConfig:
    values = load_env_values(env_path)
    url = values.get("SUPABASE_URL")
    key = values.get("SUPABASE_KEY")
    missing = [name for name, value in {"SUPABASE_URL": url, "SUPABASE_KEY": key}.items() if not value]
    if missing:
        raise RuntimeError(f"Missing Supabase env var(s): {', '.join(missing)}")
    return SupabaseConfig(url=url or "", key=key or "")


def require_neo4j_config(env_path: Path, fallback_env_path: Path) -> Neo4jConfig:
    values = load_env_values(env_path, fallback_env_path)
    uri = values.get("NEO4J_URI")
    username = values.get("NEO4J_USERNAME") or "neo4j"
    password = values.get("NEO4J_PASSWORD")
    database = values.get("NEO4J_DATABASE") or None
    missing = [name for name, value in {"NEO4J_URI": uri, "NEO4J_PASSWORD": password}.items() if not value]
    if missing:
        raise RuntimeError(f"Missing Neo4j env var(s): {', '.join(missing)}")
    return Neo4jConfig(uri=uri or "", username=username, password=password or "", database=database)


def make_supabase_client(config: SupabaseConfig):
    from supabase import create_client

    return create_client(config.url, config.key)


def fetch_all_rows(client: Any, table_name: str, select_columns: str, order_column: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = 0

    while True:
        response = (
            client.table(table_name)
            .select(select_columns)
            .order(order_column)
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


def compute_image_stats(image_rows: list[dict[str, Any]]) -> dict[str, Any]:
    verified_rows = [
        row
        for row in image_rows
        if row.get("is_checked") is True and row.get("is_drop") is False
    ]
    return {
        "source": "Supabase live: image where is_checked=true and is_drop=false",
        "verified_count": len(verified_rows),
        "raw_total": len(image_rows),
        "dropped_count": sum(1 for row in image_rows if row.get("is_drop") is True),
        "unchecked_count": sum(1 for row in image_rows if row.get("is_checked") is not True),
    }


def compute_vqa_stats(vqa_rows: list[dict[str, Any]]) -> dict[str, Any]:
    raw_split_counts = Counter(normalize_split(row.get("split")) for row in vqa_rows)
    unknown_split_counts = {
        split: count
        for split, count in raw_split_counts.items()
        if split not in CANONICAL_SPLITS
    }
    counted_rows = [row for row in vqa_rows if should_count_vqa_row(row)]

    canonical_split_counts = Counter(
        normalize_split(row.get("split")) for row in counted_rows
    )
    canonical_split_counts_dict = {
        split: canonical_split_counts.get(split, 0)
        for split in CANONICAL_SPLITS
    }

    image_ids = {norm_text(row.get("image_id")) for row in counted_rows if norm_text(row.get("image_id"))}
    qtypes = Counter(norm_text(row.get("qtype")) or "<empty>" for row in counted_rows)
    empty_triples_used = 0
    for row in counted_rows:
        triples_used = parse_jsonish(row.get("triples_used"))
        if not isinstance(triples_used, list) or len(triples_used) == 0:
            empty_triples_used += 1

    counted_test_decisions = Counter(
        norm_text(row.get("verify_decision")) or "<null>"
        for row in counted_rows
        if normalize_split(row.get("split")) == "test"
    )

    return {
        "source": (
            "Supabase live: vqa split-aware policy "
            "(globally excludes is_drop=true and empty triples_used; test also requires is_checked=true)"
        ),
        "canonical_total": len(counted_rows),
        "canonical_split_counts": canonical_split_counts_dict,
        "canonical_unique_image_ids": len(image_ids),
        "canonical_qtype_distribution": sorted_counter(qtypes),
        "canonical_empty_triples_used": empty_triples_used,
        "raw_total": len(vqa_rows),
        "raw_split_counts": sorted_counter(raw_split_counts),
        "unknown_split_counts": dict(sorted(unknown_split_counts.items())),
        "counted_test_verify_decision_distribution": sorted_counter(counted_test_decisions),
    }


def collect_supabase_stats(config: SupabaseConfig) -> dict[str, Any]:
    client = make_supabase_client(config)
    image_rows = fetch_all_rows(
        client,
        "image",
        "image_id,is_checked,is_drop",
        "image_id",
    )
    vqa_rows = fetch_all_rows(
        client,
        "vqa",
        "vqa_id,image_id,qtype,split,is_checked,is_drop,verify_decision,triples_used",
        "vqa_id",
    )
    return {
        "image": compute_image_stats(image_rows),
        "vqa": compute_vqa_stats(vqa_rows),
    }


def run_scalar(session: Any, query: str) -> int:
    record = session.run(query).single()
    if record is None:
        return 0
    return int(record["count"])


def collect_neo4j_stats(config: Neo4jConfig) -> dict[str, Any]:
    try:
        from neo4j import GraphDatabase
    except ImportError as exc:
        raise RuntimeError("neo4j driver is not installed. Run: pip install neo4j") from exc

    driver = GraphDatabase.driver(config.uri, auth=(config.username, config.password))
    try:
        driver.verify_connectivity()
        session_kwargs = {"database": config.database} if config.database else {}
        with driver.session(**session_kwargs) as session:
            total_nodes = run_scalar(session, "MATCH (n) RETURN count(n) AS count")
            total_edges = run_scalar(session, "MATCH ()-[r]->() RETURN count(r) AS count")

            entity_types = [
                {"label": row["label"], "count": row["count"]}
                for row in session.run(
                    """
                    MATCH (n)
                    UNWIND labels(n) AS label
                    RETURN label, count(n) AS count
                    ORDER BY count DESC, label
                    """
                )
            ]
            relationship_types = [
                {"type": row["type"], "count": row["count"]}
                for row in session.run(
                    """
                    MATCH ()-[r]->()
                    RETURN type(r) AS type, count(r) AS count
                    ORDER BY count DESC, type
                    """
                )
            ]
            node_label_sets = [
                {"labels": row["labels"], "count": row["count"]}
                for row in session.run(
                    """
                    MATCH (n)
                    RETURN labels(n) AS labels, count(n) AS count
                    ORDER BY count DESC
                    """
                )
            ]
            source_distribution = [
                {"source": row["source"], "count": row["count"]}
                for row in session.run(
                    """
                    MATCH ()-[r]->()
                    WITH CASE
                      WHEN r.source_url IS NULL OR trim(toString(r.source_url)) = ''
                        THEN 'Missing source'
                      WHEN toString(r.source_url) STARTS WITH 'http'
                        THEN 'Web source'
                      WHEN r.source_url IN $llm_sources
                        THEN 'LLM reasoning'
                      ELSE 'Other'
                    END AS source
                    RETURN source, count(*) AS count
                    ORDER BY count DESC, source
                    """,
                    llm_sources=sorted(LLM_SOURCE_VALUES),
                )
            ]
    finally:
        driver.close()

    return {
        "source": "Neo4j Aura live instance",
        "total_nodes": total_nodes,
        "total_edges": total_edges,
        "entity_type_count": len(entity_types),
        "relationship_type_count": len(relationship_types),
        "entity_types": entity_types,
        "relationship_types": relationship_types,
        "node_label_sets": node_label_sets,
        "source_distribution": source_distribution,
    }


def build_report(
    *,
    supabase_env: Path,
    neo4j_env: Path,
    neo4j_fallback_env: Path,
    skip_neo4j: bool,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "policy": {
            "kg_metrics": "Neo4j Aura live instance only",
            "image_metrics": "Supabase image where is_checked=true and is_drop=false",
            "vqa_metrics": (
                "Supabase vqa split-aware: globally excludes is_drop=true and empty triples_used; "
                "test additionally requires is_checked=true"
            ),
            "verify_decision": "Reported as audit metadata; not required for canonical VQA count",
        },
    }

    supabase_config = require_supabase_config(supabase_env)
    report["supabase"] = collect_supabase_stats(supabase_config)

    if skip_neo4j:
        report["neo4j"] = {"skipped": True, "reason": "Skipped by --skip-neo4j"}
    else:
        neo4j_config = require_neo4j_config(neo4j_env, neo4j_fallback_env)
        report["neo4j"] = collect_neo4j_stats(neo4j_config)

    return report


def format_table(rows: list[tuple[str, Any]]) -> list[str]:
    lines = ["| Metric | Value |", "| --- | ---: |"]
    for key, value in rows:
        lines.append(f"| {key} | {value} |")
    return lines


def format_distribution(rows: dict[str, int], name_column: str) -> list[str]:
    lines = [f"| {name_column} | Count |", "| --- | ---: |"]
    for key, value in rows.items():
        lines.append(f"| `{key}` | {value} |")
    return lines


def format_markdown(report: dict[str, Any]) -> str:
    supabase = report.get("supabase", {})
    image = supabase.get("image", {})
    vqa = supabase.get("vqa", {})
    neo4j = report.get("neo4j", {})

    lines = [
        "# Ground-Truth Metrics Snapshot",
        "",
        f"Generated at UTC: `{report.get('generated_at_utc')}`",
        "",
        "## Canonical Counts",
        "",
        *format_table(
            [
                ("Verified images (Supabase live)", image.get("verified_count", "n/a")),
                ("Canonical VQA rows (Supabase live)", vqa.get("canonical_total", "n/a")),
                ("KG nodes (Neo4j live)", neo4j.get("total_nodes", "n/a")),
                ("KG triples / relationships (Neo4j live)", neo4j.get("total_edges", "n/a")),
                ("KG entity types (Neo4j live)", neo4j.get("entity_type_count", "n/a")),
                ("KG relationship types (Neo4j live)", neo4j.get("relationship_type_count", "n/a")),
            ]
        ),
        "",
        "## VQA By Split",
        "",
        *format_distribution(vqa.get("canonical_split_counts", {}), "Split"),
        "",
        "## Supabase Diagnostics",
        "",
        *format_table(
            [
                ("Raw image rows", image.get("raw_total", "n/a")),
                ("Dropped image rows", image.get("dropped_count", "n/a")),
                ("Unchecked image rows", image.get("unchecked_count", "n/a")),
                ("Raw VQA rows", vqa.get("raw_total", "n/a")),
                ("Canonical unique VQA image IDs", vqa.get("canonical_unique_image_ids", "n/a")),
                ("Canonical rows with empty triples_used", vqa.get("canonical_empty_triples_used", "n/a")),
            ]
        ),
        "",
        "Raw VQA split counts:",
        "",
        *format_distribution(vqa.get("raw_split_counts", {}), "Split"),
    ]

    if vqa.get("unknown_split_counts"):
        lines.extend(
            [
                "",
                "Unknown VQA split counts:",
                "",
                *format_distribution(vqa["unknown_split_counts"], "Split"),
            ]
        )

    lines.extend(
        [
            "",
            "Counted test `verify_decision` distribution:",
            "",
            *format_distribution(vqa.get("counted_test_verify_decision_distribution", {}), "verify_decision"),
            "",
            "## Canonical VQA QType Distribution",
            "",
            *format_distribution(vqa.get("canonical_qtype_distribution", {}), "QType"),
        ]
    )

    if neo4j.get("skipped"):
        lines.extend(["", "## Neo4j Diagnostics", "", f"Neo4j skipped: {neo4j.get('reason')}"])
        return "\n".join(lines)

    lines.extend(
        [
            "",
            "## Neo4j Relationship Types",
            "",
            "| Relationship | Count |",
            "| --- | ---: |",
        ]
    )
    for row in neo4j.get("relationship_types", []):
        lines.append(f"| `{row['type']}` | {row['count']} |")

    lines.extend(["", "## Neo4j Entity Types", "", "| Label | Count |", "| --- | ---: |"])
    for row in neo4j.get("entity_types", []):
        lines.append(f"| `{row['label']}` | {row['count']} |")

    lines.extend(["", "## Neo4j Source Distribution", "", "| Source | Count |", "| --- | ---: |"])
    for row in neo4j.get("source_distribution", []):
        lines.append(f"| {row['source']} | {row['count']} |")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect canonical ViFoodVQA counts from Supabase and Neo4j without modifying data."
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format. Default: markdown.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional output path. If omitted, prints to stdout.",
    )
    parser.add_argument(
        "--supabase-env",
        type=Path,
        default=DEFAULT_SUPABASE_ENV,
        help=f"Supabase .env path. Default: {DEFAULT_SUPABASE_ENV}",
    )
    parser.add_argument(
        "--neo4j-env",
        type=Path,
        default=DEFAULT_NEO4J_ENV,
        help=f"Neo4j primary .env path. Default: {DEFAULT_NEO4J_ENV}",
    )
    parser.add_argument(
        "--neo4j-fallback-env",
        type=Path,
        default=DEFAULT_NEO4J_FALLBACK_ENV,
        help=f"Neo4j fallback .env path. Default: {DEFAULT_NEO4J_FALLBACK_ENV}",
    )
    parser.add_argument(
        "--skip-neo4j",
        action="store_true",
        help="Collect Supabase stats only.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = build_report(
            supabase_env=args.supabase_env,
            neo4j_env=args.neo4j_env,
            neo4j_fallback_env=args.neo4j_fallback_env,
            skip_neo4j=args.skip_neo4j,
        )
    except Exception as exc:
        print(f"[ERROR] Failed to collect ground-truth stats: {exc}", file=sys.stderr)
        return 1

    if args.format == "json":
        output = json.dumps(report, ensure_ascii=False, indent=2)
    else:
        output = format_markdown(report)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
    else:
        print(output)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
