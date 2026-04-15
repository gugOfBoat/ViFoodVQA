# ViFoodVQA — VQA Generation Module

## Purpose

This module generates **grounded multiple-choice Visual Question Answering (VQA)** samples by retrieving relevant knowledge triples from the Neo4j Knowledge Graph and prompting Google Gemini to produce Vietnamese-language questions.

## What this module is responsible for

- Retrieving local subgraph paths from Neo4j via `KGRetriever`
- Constructing answer candidates from retrieved triples (1-hop, 2-hop, substitution)
- Building distractor choices from the KG
- Prompting Gemini to generate question + rationale
- Checkpointing progress and writing output JSON
- Importing generated VQA into Supabase
- Debugging missing VQA coverage
- Splitting the VQA dataset

## What this module is NOT responsible for

- Building or modifying the Knowledge Graph (that's `ViFoodKG/`)
- Human verification or annotation (that's `streamlit/`)
- Supabase schema management (that's `supabase/`)

## Structure

```
ViFoodVQA/
├── src/
│   ├── 01_generate_vqa.py       ← Main VQA generation pipeline (1171 lines)
│   ├── query.py                 ← KGRetriever: Neo→Traverse→Prefilter→Rank (365 lines)
│   ├── 02_debug_missing_vqa.py  ← Debug images that failed VQA generation
│   ├── 03_split_dataset.py      ← Split VQA into train/val/test
│   └── utils/
│       ├── import_vqa.py            ← Import generated VQA into Supabase
│       ├── map_vqa_triples_to_kg.py ← Map VQA triples ↔ kg_triple_catalog
│       └── stats_vqa_by_split_qtype.py ← VQA statistics by split and qtype
├── data/
│   └── question_types.csv       ← Question type definitions (copy; canonical is ViFoodKG/data/)
├── .env                         ← Neo4j + Supabase + Gemini credentials
└── .env.example                 ← Template
```

## Entry Points

### `01_generate_vqa.py` — Main generator

```bash
# Generate VQA for all approved images
python src/01_generate_vqa.py

# Limit to 20 images for testing
python src/01_generate_vqa.py --limit-images 20

# Generate only specific question types
python src/01_generate_vqa.py --qtypes ingredients origin_locality allergen_restrictions

# Resume from page 3, increase retrieval depth
python src/01_generate_vqa.py --start-page 3 --top-k 10

# Specify output directory
python src/01_generate_vqa.py --output-dir /path/to/output
```

**CLI arguments:**

| Argument | Default | Description |
|----------|---------|-------------|
| `--limit-images` | None | Max images to process |
| `--qtypes` | all supported | Space-separated list of question types |
| `--start-page` | 0 | Resume from this Supabase page |
| `--top-k` | 20 | Number of KG triples to retrieve per query |
| `--output-dir` | `data/vqa/` | Output directory |
| `--qtypes-per-image` | all | Limit qtypes per image |
| `--start-image-id` | None | Filter starting image ID |
| `--end-image-id` | None | Filter ending image ID |
| `--image-ids-file` | None | File of image IDs to process |
| `--device` | auto | Embedding model device: `auto`, `cuda`, `cpu` |
| `--seed` | 42 | Random seed for reproducibility |

### `query.py` — KG Retriever (CLI + library)

```bash
# Query ingredients for Phở Bò
python src/query.py -i "Phở Bò" -q "nguyên liệu chính" -k 5

# Query allergens with JSON output
python src/query.py -i "Bánh Xèo" -q "chất gây dị ứng" -k 3 --json

# Filter by specific relations
python src/query.py -i "Phở Bò" -q "dị ứng" -k 5 --relations hasAllergen
```

**As a library:**

```python
from query import KGRetriever

with KGRetriever(device="cpu") as kg:
    results = kg.retrieve(
        items=["Phở Bò"],
        question="nguyên liệu chính",
        top_k=5,
        allowed_relations=["hasIngredient"],
    )
```

### `02_debug_missing_vqa.py` — Debug coverage gaps

```bash
python src/02_debug_missing_vqa.py
```

Reruns VQA generation for images that previously failed, with enhanced logging to diagnose `no_anchor_dish`, `retrieve_empty`, and `no_candidates` failures.

### `03_split_dataset.py` — Dataset splitting

```bash
python src/03_split_dataset.py
```

Splits VQA samples into train/val/test sets.

## Environment Variables

Required in `.env` (see `.env.example`):

| Variable | Used By | Purpose |
|----------|---------|---------|
| `NEO4J_URI` | `query.py` | Neo4j connection string |
| `NEO4J_USERNAME` | `query.py` | Neo4j username (default: `neo4j`) |
| `NEO4J_PASSWORD` | `query.py` | Neo4j password |
| `SUPABASE_URL` | `01_generate_vqa.py` | Supabase API URL |
| `SUPABASE_KEY` | `01_generate_vqa.py` | Supabase API key |
| `GEMINI_API_KEY` | `01_generate_vqa.py` | Google Gemini API key |
| `VQA_GEMINI_MODEL` | `01_generate_vqa.py` | Gemini model name (default: `gemini-3.1-flash-lite-preview`) |

## Retrieval Strategy

The `KGRetriever` class in `query.py` implements the **Neo → Traverse → Prefilter → Rank** strategy:

```
1. Neo       → Match Dish nodes by name from food_items
2. Traverse  → Cypher query: 1-hop direct + 2-hop via Ingredient + SubstitutionRule paths
3. Prefilter → If allowed_relations given, drop non-matching rows BEFORE ranking
4. Rank      → Encode full path text with multilingual-e5-small, cosine vs. query vector
```

**Key design point:** Ranking uses full path text (e.g., `"Phở bò có thành phần thịt bò; thịt bò có chất gây dị ứng Gluten"`) instead of individual edge embeddings. This ensures 2-hop paths score fairly against 1-hop.

See `docs/retrieve_logic_changes_report.md` for full rationale.

## Supported Question Types

Defined in `data/question_types.csv`:

| QType | Primary Relation | Hop | Candidate Constructor |
|-------|-----------------|-----|----------------------|
| `ingredients` | `hasIngredient` | 1 | `simple_candidates()` |
| `cooking_technique` | `cookingTechnique` | 1 | `simple_candidates()` |
| `flavor_profile` | `flavorProfile` | 1 | `simple_candidates()` |
| `origin_locality` | `originRegion` | 1 | `simple_candidates()` |
| `food_pairings` | `servedWith` | 1 | `simple_candidates()` |
| `dish_classification` | `dishType` | 1 | `simple_candidates()` |
| `ingredient_category` | `ingredientCategory` | 2 | `two_hop_candidates()` |
| `allergen_restrictions` | `hasAllergen` | 2 | `two_hop_candidates()` |
| `dietary_restrictions` | `hasDietaryTag` | 2 | `dietary_candidates()` |
| `substitution_rules` | `fromIngredient`/`toIngredient` | 2 | `substitution_candidates()` |

## Artifacts

| Artifact | Path | Format |
|----------|------|--------|
| Generated VQA | `data/vqa/generated_vqa.json` | JSON array of VQA objects |
| Progress checkpoint | `data/vqa/_generate_vqa_progress.json` | JSON with page number + accumulated results |
| Split statistics | `vqa_split_stats.csv` | CSV |
| Split statistics (LaTeX) | `vqa_split_stats.tex` | LaTeX table |

## Change Impact

| Change | Impact |
|--------|--------|
| Modify `_TRAVERSE_QUERY` in `query.py` | All VQA generation affected; test with CLI first |
| Change `_RELATION_TO_VI` mapping | Affects `rank_text` construction → changes retrieval ranking |
| Add a new question type | Must add entry in `question_types.csv` + candidate constructor in `select_candidates()` |
| Change embedding model | Must also update `05_kg_vectorizer.py` and clear `_text_embedding_cache` |
| Modify `INDIFOODVQA_PROMPT_TEMPLATE` | Affects Gemini output format; test parsing with `--limit-images 5` |

## What to Test After Changes

```bash
# 1. Test retrieval independently
python src/query.py -i "Phở Bò" -q "nguyên liệu" -k 5
python src/query.py -i "Bún Chả" -q "vùng miền" -k 3 --relations originRegion

# 2. Test VQA generation with small batch
python src/01_generate_vqa.py --limit-images 5

# 3. Verify specific question types
python src/01_generate_vqa.py --limit-images 5 --qtypes allergen_restrictions dietary_restrictions
```

## See Also

- [docs/architecture.md](../docs/architecture.md) — system architecture and artifact flow
- [docs/contracts/triple_schema.md](../docs/contracts/triple_schema.md) — triple JSON contract
- [docs/contracts/ontology_config.md](../docs/contracts/ontology_config.md) — ontology governance
- [AGENTS.md](../AGENTS.md) — coding agent guide with safe change rules
