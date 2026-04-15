<div align="center">
  <img src="https://img.shields.io/badge/Neo4j-008CC1?style=for-the-badge&logo=neo4j&logoColor=white" />
  <img src="https://img.shields.io/badge/Gemini-8E75B2?style=for-the-badge&logo=google-gemini&logoColor=white" />
  <img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white" />
  <img src="https://img.shields.io/badge/Supabase-3FCF8E?style=for-the-badge&logo=supabase&logoColor=white" />

  # 🍜 ViFoodKG
  ### Vietnamese Food Knowledge Graph for Visual Question Answering
</div>

---

**ViFoodKG** is a research project that builds a Knowledge Graph of Vietnamese cuisine and uses it for **grounded Visual Question Answering (VQA)**. The system extracts culinary knowledge from Wikipedia and LLM reasoning, stores it in a Neo4j graph with vector-indexed edges, and generates multiple-choice questions that are verified by human annotators.

## Repository Structure

This repository contains three main modules:

| Module | Description | Docs |
|--------|-------------|------|
| [`ViFoodKG/`](ViFoodKG/) | Knowledge Graph construction pipeline — 5 stages from entity extraction to graph vectorization | [README](ViFoodKG/README.md) |
| [`ViFoodVQA/`](ViFoodVQA/) | VQA sample generation using KG retrieval + Gemini | [README](ViFoodVQA/README.md) |
| [`streamlit/`](streamlit/) | Annotation & verification tool for VQA quality control | [README](streamlit/README.md) |

**Shared resources:**

| Path | Purpose |
|------|---------|
| `config/ontology_config.json` | Ontology schema — 10 entity types, 12 relations, 11 question types |
| `config/Question Type.md` | Human-readable question type reference |
| `supabase/` | PostgreSQL migration scripts (ordered: 000 → 001 → 002) |
| `docs/` | Architecture, contracts, and analysis reports |

## How it Works

```
Wikipedia + LLM  ──►  Knowledge Graph (Neo4j)  ──►  VQA Generation  ──►  Human Verification
                      10 entity types                via Gemini           Streamlit app
                      12 relations                    grounded in KG       annotation rubric
                      vector-indexed edges            multiple-choice      KEEP/DROP workflow
```

**Detailed pipeline:**

1. **Entity Extraction** — Extract food labels from image database (Supabase)
2. **Entity Classification** — Normalize and classify via Gemini
3. **Triple Extraction** — Web-grounded + LLM reasoning knowledge extraction
4. **Neo4j Ingestion** — Load into graph with MERGE (idempotent)
5. **Vectorization** — Embed edge text for hybrid retrieval
6. **VQA Generation** — Retrieve KG triples → build candidates → generate questions via Gemini
7. **Human Verification** — Streamlit annotation tool with rubric-based scoring

See [`docs/architecture.md`](docs/architecture.md) for the full architecture and artifact flow.

## Setup

### Prerequisites

- Python ≥ 3.11
- [Neo4j AuraDB](https://neo4j.com/cloud/aura/) instance (or local Neo4j)
- [Supabase](https://supabase.com/) project with the image/VQA schema
- [Google Gemini API](https://ai.google.dev/) key

### 1. Clone & Install

```bash
git clone https://github.com/gugOfBoat/vifoodKG.git
cd vifoodKG

# Install all dependencies (KG pipeline + VQA generation share the same deps)
cd ViFoodKG
pip install -e ".[dev]"
```

### 2. Configure Environment

Each module needs its own `.env` file. Copy the examples:

```bash
cp ViFoodKG/.env.example ViFoodKG/.env
cp ViFoodVQA/.env.example ViFoodVQA/.env
```

Fill in:
- `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`
- `SUPABASE_URL`, `SUPABASE_KEY`
- `GEMINI_API_KEY`

For the Streamlit app, configure `streamlit/.streamlit/secrets.toml`:
```toml
SUPABASE_KEY = "your_key_here"
```

### 3. Initialize the Database

Run the Supabase migrations in order:

```sql
-- Run in Supabase SQL Editor
-- 1. Base tables
-- supabase/000_image_vqa_triple.sql

-- 2. Extended schema + mapping tables
-- supabase/001_vqa_kg_triple_map.sql

-- 3. Edit log table
-- supabase/002_kg_triple_edit_log.sql
```

## Common Workflows

### Run the KG pipeline (stages 1–5)

```bash
cd ViFoodKG
python src/01_kg_entity_extractor.py
python src/02_kg_entity_classifier.py
python src/03_kg_triple_extractor.py
python src/04_kg_neo4j_ingestor.py
python src/05_kg_vectorizer.py
```

### Query the KG

```bash
cd ViFoodVQA
python src/query.py -i "Phở Bò" "Thịt Bò" -q "nguyên liệu chính" -k 5
python src/query.py -i "Bánh Xèo" -q "chất gây dị ứng" -k 3 --json
```

### Generate VQA samples

```bash
cd ViFoodVQA
python src/01_generate_vqa.py --limit-images 20
python src/01_generate_vqa.py --qtypes ingredients origin_locality
```

### Run the annotation tool

```bash
cd streamlit
pip install -r requirements.txt
streamlit run app.py
```

## Deeper Documentation

| Doc | Purpose |
|-----|---------|
| [`AGENTS.md`](AGENTS.md) | Coding agent guide: module map, safe changes, change impact |
| [`docs/architecture.md`](docs/architecture.md) | System architecture and artifact flow |
| [`docs/contracts/triple_schema.md`](docs/contracts/triple_schema.md) | Triple JSON interface contract |
| [`docs/contracts/ontology_config.md`](docs/contracts/ontology_config.md) | Ontology governance and change impact |
| [`docs/VERIFY_VQA_GUIDELINE.md`](docs/VERIFY_VQA_GUIDELINE.md) | VQA verification rubric for annotators |
| [`docs/KNOWLEDGE_GAP_REPORT.md`](docs/KNOWLEDGE_GAP_REPORT.md) | KG coverage analysis and enrichment results |
| [`docs/retrieve_logic_changes_report.md`](docs/retrieve_logic_changes_report.md) | Retrieval strategy evolution |

## License

This project is developed as part of academic research at HCMUS.
