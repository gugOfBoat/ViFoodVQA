from __future__ import annotations

import csv
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .config import resolve_project_path
from .data import VQASample
from .triples import dedupe_triples, expand_path_rows, normalize_text, slug


@dataclass(frozen=True)
class QTypeMeta:
    qtype: str
    keywords: str
    description: str
    relations: list[str]


class EvaluationRetriever:
    def __init__(self, cfg: dict[str, Any], device: str = "auto") -> None:
        vqa_src_dir = resolve_project_path(cfg, cfg["paths"]["vqa_src_dir"])
        sys.path.insert(0, str(vqa_src_dir))

        from query import KGRetriever, _TRAVERSE_QUERY, _build_rank_text

        self._traverse_query = _TRAVERSE_QUERY
        self._build_rank_text = _build_rank_text
        self.kg = KGRetriever(device=device)
        self.top_k = int(cfg["evaluation"]["top_k"])
        self.qtypes = load_qtype_meta(resolve_project_path(cfg, cfg["paths"]["kg_question_types_csv"]))
        self.dish_map = self._fetch_dish_map()
        self._global_rows: list[dict[str, Any]] | None = None
        self._global_texts: list[str] | None = None

    def close(self) -> None:
        self.kg.close()

    def match_items(self, items: list[str]) -> list[str]:
        matched = []
        for item in items:
            name = self.dish_map.get(slug(item))
            if name and name not in matched:
                matched.append(name)
        return matched

    def retrieve(
        self,
        sample: VQASample,
        strategy: str,
        classifier: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if strategy == "oracle":
            return sample.gold_triples

        qtype = classifier.get("qtype") or sample.row.get("qtype")
        items = self.match_items(classifier.get("food_items") or [])
        if strategy in {"hybrid", "graph_only"} and not items:
            return []

        meta = self.qtypes.get(str(qtype))
        query = build_retrieval_query(meta, sample.row["question"], items)

        if strategy == "hybrid":
            return self._hybrid(items, query, meta)
        if strategy == "graph_only":
            return self._graph_only(items, meta)
        if strategy == "vector_only":
            return self._vector_only(query)
        if strategy == "bm25":
            return self._bm25(query)
        raise ValueError(f"Unknown retrieval strategy: {strategy}")

    def _hybrid(self, items: list[str], query: str, meta: QTypeMeta | None) -> list[dict[str, Any]]:
        rows = self.kg.retrieve(
            items=items,
            question=query,
            top_k=self.top_k * 2,
            allowed_relations=meta.relations if meta else None,
        )
        return expand_path_rows(rows, limit=self.top_k)

    def _graph_only(self, items: list[str], meta: QTypeMeta | None) -> list[dict[str, Any]]:
        rows = self._traverse(items)
        if meta and meta.relations:
            allowed = set(meta.relations)
            rows = [row for row in rows if row.get("relation") in allowed]
        rows.sort(
            key=lambda row: (
                int(row.get("hop") or 0),
                normalize_text(row.get("subject")),
                normalize_text(row.get("relation")),
                normalize_text(row.get("target")),
                normalize_text(row.get("via")),
            )
        )
        return expand_path_rows(rows, limit=self.top_k)

    def _vector_only(self, query: str) -> list[dict[str, Any]]:
        rows, texts = self._global_index()
        query_vec = self.kg._embed(query)
        row_vecs = self.kg._embed_many(texts)
        scored = [
            (float(np.dot(query_vec, np.array(vec, dtype=np.float32))), row)
            for row, vec in zip(rows, row_vecs, strict=True)
        ]
        scored.sort(key=lambda pair: pair[0], reverse=True)
        triples = [
            {"subject": row.get("subject"), "relation": row.get("relation"), "target": row.get("target")}
            for _, row in scored
        ]
        return dedupe_triples(triples)[: self.top_k]

    def _bm25(self, query: str) -> list[dict[str, Any]]:
        rows, texts = self._global_index()
        query_terms = _tokenize(query)
        if not query_terms:
            return []

        docs = [_tokenize(text) for text in texts]
        df = {term: sum(1 for doc in docs if term in doc) for term in set(query_terms)}
        avgdl = sum(len(doc) for doc in docs) / len(docs) if docs else 0.0
        scored = [
            (_bm25_score(doc, query_terms, df, len(docs), avgdl), row)
            for doc, row in zip(docs, rows, strict=True)
        ]
        scored.sort(
            key=lambda pair: (
                pair[0],
                normalize_text(pair[1].get("subject")),
                normalize_text(pair[1].get("target")),
            ),
            reverse=True,
        )
        triples = [
            {"subject": row.get("subject"), "relation": row.get("relation"), "target": row.get("target")}
            for score, row in scored
            if score > 0
        ]
        return dedupe_triples(triples)[: self.top_k]

    def _traverse(self, items: list[str]) -> list[dict[str, Any]]:
        with self.kg._driver.session() as session:
            return [dict(row) for row in session.run(self._traverse_query, items=items)]

    def _global_index(self) -> tuple[list[dict[str, Any]], list[str]]:
        if self._global_rows is not None and self._global_texts is not None:
            return self._global_rows, self._global_texts

        query = """
        MATCH (subject)-[r]->(target)
        RETURN DISTINCT
          subject.name AS subject,
          labels(subject)[0] AS subject_type,
          type(r) AS relation,
          target.name AS target,
          labels(target)[0] AS target_type,
          null AS via,
          null AS via_type,
          r.verbalized_text AS verbalized_text,
          r.evidence AS evidence,
          r.source_url AS source_url,
          1 AS hop
        """
        with self.kg._driver.session() as session:
            rows = [dict(row) for row in session.run(query)]
        rows = [
            row
            for row in rows
            if row.get("subject") and row.get("relation") and row.get("target")
        ]
        self._global_rows = rows
        self._global_texts = [self._build_rank_text(row) for row in rows]
        return self._global_rows, self._global_texts

    def _fetch_dish_map(self) -> dict[str, str]:
        mapping: dict[str, str] = {}
        with self.kg._driver.session() as session:
            for row in session.run("MATCH (d:Dish) RETURN d.name AS name"):
                name = str(row["name"] or "").strip()
                if name:
                    mapping[slug(name)] = name
        return mapping


def load_qtype_meta(path: Path) -> dict[str, QTypeMeta]:
    result: dict[str, QTypeMeta] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            qtype = row.get("canonical_qtype") or row.get("question_type") or ""
            relations = re.findall(r"\[([A-Za-z_]+)\]", row.get("relationship_path", ""))
            result[qtype] = QTypeMeta(
                qtype=qtype,
                keywords=row.get("keywords", ""),
                description=row.get("detailed_description") or row.get("description", ""),
                relations=relations,
            )
    return result


def build_retrieval_query(
    meta: QTypeMeta | None,
    question: str,
    items: list[str],
) -> str:
    if not meta:
        return f"Question: {question}. Items: {', '.join(items)}"
    return (
        f"Question type: {meta.qtype}. "
        f"Keywords: {meta.keywords}. "
        f"Retrieval goal: {meta.description}. "
        f"Question: {question}. "
        f"Predicted dishes: {', '.join(items)}."
    )


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\w+", normalize_text(text))


def _bm25_score(
    doc: list[str],
    query_terms: list[str],
    df: dict[str, int],
    doc_count: int,
    avgdl: float,
) -> float:
    if not doc or not avgdl:
        return 0.0
    score = 0.0
    term_counts = {term: doc.count(term) for term in set(query_terms)}
    k1 = 1.5
    b = 0.75
    for term in query_terms:
        freq = term_counts.get(term, 0)
        if not freq:
            continue
        idf = np.log(1 + (doc_count - df.get(term, 0) + 0.5) / (df.get(term, 0) + 0.5))
        denom = freq + k1 * (1 - b + b * len(doc) / avgdl)
        score += float(idf * freq * (k1 + 1) / denom)
    return score

