# Streamlit Annotation Tool

## Purpose

Web-based annotation and verification tool for ViFoodVQA quality control. Enables human annotators to review VQA samples, score them on a 3-criterion rubric, edit linked KG triples inline, and make KEEP/DROP decisions.

## What this module is responsible for

- Displaying VQA samples with linked images and KG triples
- 3-criterion rubric scoring (Q0: Triple Validity, Q1: Question Validity, Q2: Choice Quality)
- Automated KEEP/DROP recommendations based on rubric rules
- Inline triple review (Valid / Invalid / Needs edit / Unsure)
- Triple editing with revision tracking via `kg_triple_catalog` and `kg_triple_edit_log`
- Progress tracking per VQA range
- Filtering by VQA ID range, is_checked, is_drop, qtype, and split

## What this module is NOT responsible for

- KG construction (that's `ViFoodKG/`)
- VQA generation (that's `ViFoodVQA/`)
- Database schema migrations (that's `supabase/`)

## Structure

```
streamlit/
├── app.py                 ← Main application (1778 lines)
├── requirements.txt       ← Python dependencies
├── supabase_schema.sql    ← Copy of supabase/000_image_vqa_triple.sql (canonical: supabase/)
├── data/
│   └── question_types.csv ← Copy (canonical: ViFoodKG/data/)
├── .streamlit/
│   └── secrets.toml       ← SUPABASE_KEY for deployment
├── .devcontainer/
│   └── devcontainer.json  ← GitHub Codespaces configuration
└── README.md              ← This file
```

## Quick Start

### Local

```bash
cd streamlit
pip install -r requirements.txt
streamlit run app.py
```

The app will be available at `http://localhost:8501`.

### GitHub Codespaces

This module includes a `.devcontainer/devcontainer.json` that:
1. Uses Python 3.11
2. Installs `requirements.txt` on container creation
3. Auto-starts `streamlit run app.py` on attach
4. Forwards port 8501

### Streamlit Cloud

Deploy with `streamlit/.streamlit/secrets.toml` containing:

```toml
SUPABASE_KEY = "your_supabase_service_role_key"
```

The `SUPABASE_URL` is configured as a fallback constant in `app.py`.

## Configuration

### Required

| Setting | Source | Description |
|---------|--------|-------------|
| `SUPABASE_KEY` | `secrets.toml` or env var | Supabase API key (required) |

### Optional

| Setting | Default | Description |
|---------|---------|-------------|
| `SUPABASE_URL` | Hardcoded in `app.py` | Supabase project URL |
| `PAGE_SIZE` | `1000` | Rows per Supabase API page |

### Supabase Tables Required

| Table | Required | Used For |
|-------|----------|----------|
| `image` | ✅ Yes | Image metadata, URLs, food_items |
| `vqa` | ✅ Yes | VQA samples, verification state |
| `kg_triple_catalog` | ⬚ Optional | Triple deduplication, global review state |
| `vqa_kg_triple_map` | ⬚ Optional | VQA ↔ triple mapping, per-VQA review state |
| `kg_triple_edit_log` | ⬚ Optional | Audit trail for inline triple edits |

The app uses `table_exists()` and `column_exists()` to gracefully degrade when optional tables or columns are absent.

## Features

### VQA Verification Workflow

1. **Select VQA range** — Filter by VQA ID range, split, qtype, is_checked, is_drop
2. **View VQA** — See image, food_items, image_desc, question, choices, answer, rationale
3. **Score** — Rate on 3 criteria (Q0, Q1, Q2) using 1–4 scale
4. **Auto-recommendation** — System suggests KEEP/DROP based on rubric rules:
   - `Q0 ≤ 2` → DROP (triple quality too low)
   - `Q1 ≤ 2` → DROP (question quality too low)
   - `Q2 ≤ 2` → warning (choice quality concern)
5. **Override** — Annotator can override the auto recommendation
6. **Save** — Writes scores, decision, notes, and rule to Supabase

> **Note:** The project slide describes 4 rubric criteria (Q0–Q3, including Q3: Rationale). The current implementation and [verification guideline](../docs/VERIFY_VQA_GUIDELINE.md) use **3 criteria** (Q0–Q2). Q3 (Rationale) was descoped per guideline section 3.1: "reason is not a primary component for benchmarking."

### Triple Review (per VQA)

For each triple in `triples_used`:

| Verdict | Meaning |
|---------|---------|
| **Valid** | Triple is correct and useful for this VQA |
| **Invalid** | Triple is wrong or irrelevant; should not be used |
| **Needs edit** | Triple direction is right but details are wrong; opens inline editor |
| **Unsure** | Insufficient evidence to judge |

When **Needs edit** is selected:
- Annotator edits subject/relation/target/evidence/source_url
- App creates a **new** triple in `kg_triple_catalog` (linked to parent via `parent_triple_id`)
- `vqa_kg_triple_map` tracks the replacement
- `kg_triple_edit_log` records the audit trail
- Original triple is **never silently overwritten**

### Progress Tracking

The sidebar shows verification progress for the selected range:
- Total VQA assigned
- Verified count
- Unverified count

## Verification Guidelines

See [`docs/VERIFY_VQA_GUIDELINE.md`](../docs/VERIFY_VQA_GUIDELINE.md) for the complete rubric and scoring guide.

## Supabase Schema Dependencies

The app introspects the database at runtime. Key column dependencies:

**Required columns on `vqa`:**
- `vqa_id`, `image_id`, `qtype`, `question`, `choice_a`–`choice_d`, `answer`, `is_checked`, `is_drop`

**Optional columns on `vqa`:**
- `split`, `triples_used`, `triples_retrieved`, `rationale`
- `q0_score`, `q1_score`, `q2_score`, `verify_decision`, `verify_notes`, `verify_rule`

**Column detection logic:**
The app uses `column_exists(table, column)` before every optional column access. This is cached with 120s TTL.

## Change Impact

| Change | Impact |
|--------|--------|
| Add Supabase column to `vqa` | Safe if optional; app will detect via `column_exists()` |
| Remove Supabase column from `vqa` | May break if app expects it; check `VERIFY_FIELD_CANDIDATES` |
| Change `question_types.csv` | Update copy in `streamlit/data/` (canonical: `ViFoodKG/data/`) |
| Modify triple JSON schema | Check `canonicalize_triple()` and `parse_triple_list()` |
| Change Supabase URL | Update hardcoded fallback in `app.py` line 15 |

## What to Test After Changes

1. Load the app: `streamlit run app.py`
2. Filter a small VQA range (e.g., VQA 1–10)
3. Open a VQA detail — verify image, question, choices display
4. Check triple review tab — verify triples_used renders
5. Try scoring and saving — verify Supabase write succeeds
6. If optional tables are missing, verify graceful degradation (no crash)

## See Also

- [docs/VERIFY_VQA_GUIDELINE.md](../docs/VERIFY_VQA_GUIDELINE.md) — full verification rubric and scoring guide
- [docs/architecture.md](../docs/architecture.md) — system architecture
- [docs/contracts/triple_schema.md](../docs/contracts/triple_schema.md) — triple JSON contract
- [AGENTS.md](../AGENTS.md) — coding agent guide
