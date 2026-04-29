from __future__ import annotations

import re
import unicodedata
from typing import Any


def normalize_text(value: object) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFC", text)
    return " ".join(text.strip().lower().split())


def slug(value: object) -> str:
    text = unicodedata.normalize("NFKD", "" if value is None else str(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return text


def triple_key(triple: dict[str, Any]) -> tuple[str, str, str]:
    return (
        normalize_text(triple.get("subject")),
        normalize_text(triple.get("relation")),
        normalize_text(triple.get("target")),
    )


def dedupe_triples(triples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    result: list[dict[str, Any]] = []
    for triple in triples:
        key = triple_key(triple)
        if key in seen or not all(key):
            continue
        seen.add(key)
        result.append(
            {
                "subject": triple.get("subject"),
                "relation": triple.get("relation"),
                "target": triple.get("target"),
            }
        )
    return result


def expand_path_row(row: dict[str, Any]) -> list[dict[str, Any]]:
    subject = row.get("subject")
    relation = row.get("relation")
    target = row.get("target")
    via = row.get("via")

    if not via:
        return [{"subject": subject, "relation": relation, "target": target}]

    if relation in {"fromIngredient", "toIngredient"}:
        first_relation = "hasSubRule"
    else:
        first_relation = "hasIngredient"

    return [
        {"subject": subject, "relation": first_relation, "target": via},
        {"subject": via, "relation": relation, "target": target},
    ]


def expand_path_rows(rows: list[dict[str, Any]], limit: int | None = None) -> list[dict[str, Any]]:
    triples: list[dict[str, Any]] = []
    for row in rows:
        triples.extend(expand_path_row(row))
    deduped = dedupe_triples(triples)
    return deduped if limit is None else deduped[:limit]


def verbalize_triples(triples: list[dict[str, Any]], limit: int | None = None) -> str:
    selected = triples if limit is None else triples[:limit]
    if not selected:
        return "(No external triples.)"
    lines = []
    for idx, triple in enumerate(selected, start=1):
        lines.append(
            f"{idx}. {triple.get('subject')} --{triple.get('relation')}--> {triple.get('target')}"
        )
    return "\n".join(lines)

