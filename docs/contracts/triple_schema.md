# Triple JSON Schema Contract

> **Canonical source** for the triple data format used across ViFoodKG, ViFoodVQA, and the Streamlit annotation tool.

## Purpose

The "triple" is the fundamental unit of knowledge in ViFoodKG. It flows through every stage of the pipeline — from extraction to Neo4j ingestion to VQA generation to human verification. This document defines the schema, required fields, validation rules, and compatibility constraints.

## Schema

```json
{
  "subject":    "string (required)",
  "relation":   "string (required)",
  "target":     "string (required)",
  "evidence":   "string (optional, nullable)",
  "source_url": "string (optional, nullable)"
}
```

### Field Definitions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `subject` | `string` | ✅ Yes | Source entity name (typically a `Dish` or `Ingredient`). Must be non-empty after trimming. |
| `relation` | `string` | ✅ Yes | Relationship type from the ontology. Must be one of the 12 defined relation names (see below). |
| `target` | `string` | ✅ Yes | Target entity name. Must be non-empty after trimming. |
| `evidence` | `string` | ⬚ No | Textual snippet from the source that supports this triple. May be `null` or empty. |
| `source_url` | `string` | ⬚ No | URL of the web source, or one of the special values: `"LLM_Knowledge"`, `"Cognitive_Reasoning"`, `"Common_Sense"`. May be `null`. |

### Valid `relation` Values

From `config/ontology_config.json`:

| Relation | Domain → Range | Hop |
|----------|---------------|-----|
| `hasIngredient` | Dish → Ingredient | 1-hop |
| `ingredientCategory` | Ingredient → IngredientCategory | 2-hop |
| `originRegion` | Dish → Region | 1-hop |
| `dishType` | Dish → DishType | 1-hop |
| `servedWith` | Dish → SideDish | 1-hop |
| `cookingTechnique` | Dish → CookingTechnique | 1-hop |
| `flavorProfile` | Dish → FlavorProfile | 1-hop |
| `hasAllergen` | Ingredient → Allergen | 2-hop |
| `hasDietaryTag` | Ingredient → DietaryTag | 2-hop |
| `hasSubRule` | Dish → SubstitutionRule | 1-hop (reification) |
| `fromIngredient` | SubstitutionRule → Ingredient | part of reification |
| `toIngredient` | SubstitutionRule → Ingredient | part of reification |

## Upstream Producers

| Producer | Location | Notes |
|----------|----------|-------|
| `03_kg_triple_extractor.py` | `ViFoodKG/src/` | Writes `data/triples/*.json` — one JSON array of triples per entity. May include additional fields like `confidence` which downstream stages ignore. |
| `01_generate_vqa.py` | `ViFoodVQA/src/` | Writes `triples_used` arrays into the `vqa` table. Uses the minimal `{subject, relation, target}` form (evidence/source_url may be absent). |
| Streamlit triple editor | `streamlit/app.py` | Creates revised triples via `ensure_catalog_triple()` when a verifier submits an inline edit. |

## Downstream Consumers

| Consumer | Location | How it Uses Triples |
|----------|----------|-------------------|
| `04_neo4j_ingestor.py` | `ViFoodKG/src/` | Reads `data/triples/*.json`, creates Neo4j nodes + relationships. Expects `subject`, `relation`, `target`. Uses `evidence` and `source_url` as edge properties. |
| `05_kg_vectorizer.py` | `ViFoodKG/src/` | Reads `verbalized_text` property on Neo4j edges (set by the ingestor). Not directly a JSON consumer. |
| `query.py` | `ViFoodVQA/src/` | Returns triples from Neo4j Cypher traversal. Adds runtime fields: `subject_type`, `target_type`, `via`, `via_type`, `hop`, `rank_text`, `score`. |
| `01_generate_vqa.py` | `ViFoodVQA/src/` | Reads retrieved triples from `query.py`, selects candidates, writes `triples_used` to output. Uses `shrink_triples()` to reduce to `{subject, relation, target}`. |
| `streamlit/app.py` | `streamlit/` | Reads `triples_used` from the `vqa` table via `parse_triple_list()` and `canonicalize_triple()`. Displays for human review. |

## Canonicalization

The Streamlit app normalizes triples on read via `canonicalize_triple()`:

```python
def canonicalize_triple(item: dict) -> dict | None:
    subject = norm_text(item.get("subject"))
    relation = norm_text(item.get("relation"))
    target = norm_text(item.get("target"))
    if not subject or not relation or not target:
        return None
    return {
        "subject": subject,
        "relation": relation,
        "target": target,
        "evidence": norm_text(item.get("evidence")) or None,
        "source_url": norm_text(item.get("source_url")) or None,
    }
```

**Rules:**
- All string values are stripped of leading/trailing whitespace
- `subject`, `relation`, `target` must all be non-empty after stripping; if any is empty, the triple is dropped
- `evidence` and `source_url` are normalized to `None` if empty

## Storage Locations

### 1. File system — `data/triples/*.json`

Array of triple objects. May contain extra fields from extraction (e.g., `confidence`). One file per entity slug.

```json
[
  {
    "subject": "Phở Bò",
    "relation": "hasIngredient",
    "target": "Thịt Bò",
    "evidence": "Phở bò sử dụng thịt bò làm nguyên liệu chính.",
    "source_url": "https://vi.wikipedia.org/wiki/Phở",
    "confidence": "high"
  }
]
```

### 2. Supabase — `vqa.triples_used` (JSONB column)

Array of minimal triple objects. Written by `01_generate_vqa.py`, read by `streamlit/app.py`.

```json
[
  {"subject": "Phở Bò", "relation": "hasIngredient", "target": "Thịt Bò"},
  {"subject": "Phở Bò", "relation": "hasIngredient", "target": "Bánh Phở"}
]
```

### 3. Supabase — `kg_triple_catalog` table

Relational storage with unique constraint on `(subject, relation, target)`. Columns: `triple_id`, `subject`, `relation`, `target`, `evidence`, `source_url`, `is_checked`, `is_drop`, `created_from`, `parent_triple_id`, `needs_review`.

### 4. Neo4j — Graph edges

Each relationship has properties: `verbalized_text`, `evidence`, `source_url`, `embedding` (384-dim float array).

## Failure Modes

| Failure | Cause | Effect |
|---------|-------|--------|
| Missing `subject`/`relation`/`target` | Extraction returned incomplete data | Triple silently dropped by `canonicalize_triple()` |
| Unknown `relation` value | Ontology mismatch or typo | Neo4j ingestor may create unexpected relationship types; `select_candidates()` won't match it to any qtype |
| Duplicate triples | Multiple extraction runs | Neo4j ingestor uses `MERGE` (safe); `kg_triple_catalog` has unique constraint (safe) |
| `evidence` too long | Wikipedia article fully quoted | No hard limit enforced, but Gemini prompt context may be exceeded |
| `source_url` missing | LLM-generated triple without URL | Acceptable if marked as `"LLM_Knowledge"` |

## Compatibility Risks

1. **Adding a field** to the triple schema is safe — all consumers use dictionary access with `.get()` and ignore unknown keys.
2. **Removing a required field** (`subject`, `relation`, `target`) will break `canonicalize_triple()` and `MERGE` queries in the ingestor.
3. **Renaming a field** (e.g., `target` → `object`) will silently break all consumers with no error — they'll just get `None` from `.get("target")`.
4. **Changing `relation` values** requires updates to `_RELATION_TO_VI` in `query.py`, `select_candidates()` in `01_generate_vqa.py`, and `_TRAVERSE_QUERY` Cypher.

## Validation Checklist

Before committing changes to triple-related code:

- [ ] All 3 required fields (`subject`, `relation`, `target`) are present
- [ ] `relation` value matches one of the 12 ontology relations
- [ ] New fields use `None` as default (not empty string)
- [ ] `canonicalize_triple()` in `app.py` handles the change
- [ ] `shrink_triples()` in `01_generate_vqa.py` handles the change
- [ ] Neo4j ingestor MERGE queries still work
- [ ] `kg_triple_catalog` unique constraint is compatible

## See Also

- [docs/architecture.md](../architecture.md) — system architecture and artifact flow
- [docs/contracts/ontology_config.md](ontology_config.md) — ontology governance (relation names used in triples)
- [AGENTS.md](../../AGENTS.md) — coding agent guide with safe change rules
