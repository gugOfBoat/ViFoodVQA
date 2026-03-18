"""
Step 5 - Generate ViFoodVQA samples from Neo4j KG + Supabase image metadata.

Pipeline
--------
1. Read images from Supabase table `image` (description + food_items)
2. Link a visible main dish in each image to Neo4j
3. Retrieve KG facts relevant to a question type
4. Build one MCQ sample with 4 choices + rationale using Gemini
5. Save JSON checkpoint + final output

Default assumptions
-------------------
- Supabase table name: image
- Image identifier column: image_id
- Image URL column: image_url
- Description column: image_desc
- Food items column: food_items
- Question types are loaded from data/question_types.csv
- KG nodes already loaded into Neo4j by 04_kg_neo4j_ingestor.py

Usage examples
--------------
python src/05_generate_vqa.py --limit-images 20 --qtypes-per-image 2
python src/05_generate_vqa.py --start-page 3 --limit-images 100
python src/05_generate_vqa.py --table image --id-col image_id --image-col image_url \
    --desc-col image_desc --items-col food_items

Notes
-----
- This script only supports question types that are backed by the current ViFoodKG.
- `health_and_nutritional_aspects` is intentionally skipped because the current KG ontology
  does not yet contain nutrient relations.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

QUESTION_TYPES_FILE = PROJECT_ROOT / "data" / "question_types.csv"
OUTPUT_DIR = PROJECT_ROOT / "data" / "vqa"
OUTPUT_FILE = OUTPUT_DIR / "generated_vqa.json"
PROGRESS_FILE = OUTPUT_DIR / "_vqa_progress.json"

GEMINI_MODEL = os.getenv("VQA_GEMINI_MODEL", "gemini-3.1-flash-lite-preview")
PAGE_SIZE = 200

SUPPORTED_QTYPE_ALIASES: dict[str, str] = {
    "ingredients": "ingredients",
    "ingredient": "ingredients",
    "side_dish": "side_dish",
    "side dish": "side_dish",
    "origin": "origin",
    "dish_type": "dish_type",
    "type_of_dish": "dish_type",
    "type of dish": "dish_type",
    "ingredient_category": "ingredient_category",
    "category_of_ingredient": "ingredient_category",
    "allergen_restrictions": "allergen_restrictions",
    "allergens restrictions": "allergen_restrictions",
    "cooking_technique": "cooking_technique",
    "flavor_profile": "flavor_profile",
    "taste_and_flavor_profile": "flavor_profile",
    "taste and flavor profile": "flavor_profile",
    "dietary_restrictions": "dietary_restrictions",
    "ingredient_substitutions": "ingredient_substitutions",
    "ingredient substitutions": "ingredient_substitutions",
}

UNSUPPORTED_QTYPES = {
    "health_and_nutritional_aspects",
    "health and nutritional aspects",
    "cultural_significance",
}


def norm_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text


def slug(text: str) -> str:
    cleaned = norm_text(text).lower()
    cleaned = cleaned.replace("đ", "d")
    cleaned = unicodedata.normalize("NFD", cleaned)
    cleaned = "".join(ch for ch in cleaned if unicodedata.category(ch) != "Mn")
    cleaned = re.sub(r"[^a-z0-9]+", "-", cleaned).strip("-")
    return cleaned


RELATION_VI = {
    "hasIngredient": "có nguyên liệu",
    "servedWith": "thường ăn kèm với",
    "originRegion": "có nguồn gốc từ",
    "dishType": "thuộc loại món",
    "cookingTechnique": "được chế biến bằng",
    "flavorProfile": "có hương vị",
    "ingredientCategory": "thuộc nhóm nguyên liệu",
    "hasAllergen": "có chất gây dị ứng",
    "hasDietaryTag": "mang nhãn chế độ ăn",
    "hasSubRule": "có quy tắc thay thế",
    "fromIngredient": "thay nguyên liệu gốc",
    "toIngredient": "bằng nguyên liệu",
}


GENERATION_PROMPT = """
Bạn là chuyên gia tạo dữ liệu cho benchmark ViFoodVQA.

NHIỆM VỤ:
Tạo đúng 1 mẫu câu hỏi trắc nghiệm tiếng Việt (MCQ-4) từ ảnh món ăn, mô tả ảnh, food items và tri thức KG đã retrieve sẵn.

QUY TẮC BẮT BUỘC:
1. Câu hỏi phải bám vào NGỮ CẢNH THỊ GIÁC của ảnh (màu sắc, bố cục, vị trí tương đối, món nào xuất hiện trong ảnh).
2. Không được nhắc tới "triple", "knowledge graph", "ontology".
3. Kiến thức ngoài ảnh chỉ được dùng để SUY LUẬN và giải thích trong rationale.
4. Câu hỏi phải tự nhiên, ngắn gọn, tiếng Việt chuẩn.
5. Chỉ có đúng 1 đáp án đúng.
6. KHÔNG được đổi nội dung các lựa chọn đã cho. Chỉ được sắp xếp chúng đúng vào A/B/C/D như input.
7. Rationale phải giải thích ngắn gọn vì sao đáp án đúng, dựa trên ảnh + tri thức đã retrieve.
8. Nếu thông tin ảnh không đủ để gắn với câu hỏi một cách tự nhiên, hãy trả về {"skip": true, "reason": "..."}.

ĐỊNH DẠNG JSON DUY NHẤT:
{
  "question_vi": "...",
  "choices": {
    "A": "...",
    "B": "...",
    "C": "...",
    "D": "..."
  },
  "answer": "A",
  "rationale_vi": "...",
  "skip": false
}
""".strip()


def load_question_types_csv(csv_path: Path) -> list[str]:
    if not csv_path.exists():
        raise FileNotFoundError(f"Question types CSV not found: {csv_path}")

    def is_truthy(value: str) -> bool:
        return norm_text(value).lower() in {"1", "true", "yes", "y"}

    qtypes: list[str] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw = norm_text(row.get("canonical_qtype") or row.get("qtype") or row.get("question_type") or "")
            if not raw:
                continue
            canon = SUPPORTED_QTYPE_ALIASES.get(raw.lower(), raw.lower())
            if canon in UNSUPPORTED_QTYPES:
                continue
            supported = row.get("supported_in_current_kg")
            if supported is not None and supported != "" and not is_truthy(supported):
                continue
            if canon in SUPPORTED_QTYPE_ALIASES.values() and canon not in qtypes:
                qtypes.append(canon)
    return qtypes


def load_progress() -> dict[str, Any]:
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
    return {
        "page": 0,
        "generated": [],
        "seen_keys": [],
    }


def save_progress(progress: dict[str, Any]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PROGRESS_FILE.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------

def make_supabase_client():
    from supabase import create_client

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_KEY missing in .env")
    return create_client(url, key)


def make_neo4j_driver():
    from neo4j import GraphDatabase

    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USERNAME", "neo4j")
    password = os.getenv("NEO4J_PASSWORD")
    if not password:
        raise RuntimeError("NEO4J_PASSWORD missing in .env")
    return GraphDatabase.driver(uri, auth=(user, password))


def make_gemini_client():
    from google import genai

    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY missing in .env")
    return genai.Client(api_key=key)


# ---------------------------------------------------------------------------
# Supabase image loading
# ---------------------------------------------------------------------------

def fetch_image_rows(
    client,
    table: str,
    id_col: str,
    image_col: str,
    desc_col: str,
    items_col: str,
    page: int,
    size: int,
) -> list[dict[str, Any]]:
    select_cols = f"{id_col}, {image_col}, {desc_col}, {items_col}"
    resp = (
        client.table(table)
        .select(select_cols)
        .not_.is_(items_col, "null")
        .not_.is_(desc_col, "null")
        .range(page * size, (page + 1) * size - 1)
        .execute()
    )
    return resp.data or []


# ---------------------------------------------------------------------------
# Neo4j retrieval
# ---------------------------------------------------------------------------

def fetch_dish_aliases(driver) -> dict[str, str]:
    query = "MATCH (d:Dish) RETURN d.name AS name"
    mapping: dict[str, str] = {}
    with driver.session() as session:
        rows = session.run(query)
        for row in rows:
            name = row["name"]
            mapping[slug(name)] = name
    return mapping


def choose_main_dish(food_items: list[str], dish_aliases: dict[str, str]) -> str | None:
    for item in food_items:
        key = slug(item)
        if key in dish_aliases:
            return dish_aliases[key]
    return None


def get_distractors(driver, label: str, exclude: list[str], limit: int = 3) -> list[str]:
    label = re.sub(r"[^A-Za-z0-9_]", "", label)
    query = f"MATCH (n:{label}) WHERE NOT n.name IN $exclude RETURN n.name AS name ORDER BY rand() LIMIT $limit"
    with driver.session() as session:
        rows = session.run(query, exclude=exclude, limit=limit)
        return [row["name"] for row in rows]


def retrieve_fact_candidates(driver, dish: str, qtype: str, visible_items: list[str]) -> list[dict[str, Any]]:
    visible_set = {slug(x) for x in visible_items}
    candidates: list[dict[str, Any]] = []

    query_map: dict[str, str] = {
        "ingredients": """
            MATCH (d:Dish {name:$dish})-[r:hasIngredient]->(i:Ingredient)
            RETURN d.name AS dish, i.name AS answer,
                   [{subject:d.name, relation:'hasIngredient', target:i.name, target_type:'Ingredient'}] AS triples,
                   'Ingredient' AS answer_label,
                   i.name AS anchor
        """,
        "side_dish": """
            MATCH (d:Dish {name:$dish})-[r:servedWith]->(s)
            RETURN d.name AS dish, s.name AS answer,
                   [{subject:d.name, relation:'servedWith', target:s.name, target_type:head(labels(s))}] AS triples,
                   head(labels(s)) AS answer_label,
                   s.name AS anchor
        """,
        "origin": """
            MATCH (d:Dish {name:$dish})-[r:originRegion]->(x:Region)
            RETURN d.name AS dish, x.name AS answer,
                   [{subject:d.name, relation:'originRegion', target:x.name, target_type:'Region'}] AS triples,
                   'Region' AS answer_label,
                   x.name AS anchor
        """,
        "dish_type": """
            MATCH (d:Dish {name:$dish})-[r:dishType]->(x:DishType)
            RETURN d.name AS dish, x.name AS answer,
                   [{subject:d.name, relation:'dishType', target:x.name, target_type:'DishType'}] AS triples,
                   'DishType' AS answer_label,
                   x.name AS anchor
        """,
        "cooking_technique": """
            MATCH (d:Dish {name:$dish})-[r:cookingTechnique]->(x:CookingTechnique)
            RETURN d.name AS dish, x.name AS answer,
                   [{subject:d.name, relation:'cookingTechnique', target:x.name, target_type:'CookingTechnique'}] AS triples,
                   'CookingTechnique' AS answer_label,
                   x.name AS anchor
        """,
        "flavor_profile": """
            MATCH (d:Dish {name:$dish})-[r:flavorProfile]->(x:FlavorProfile)
            RETURN d.name AS dish, x.name AS answer,
                   [{subject:d.name, relation:'flavorProfile', target:x.name, target_type:'FlavorProfile'}] AS triples,
                   'FlavorProfile' AS answer_label,
                   x.name AS anchor
        """,
        "ingredient_category": """
            MATCH (d:Dish {name:$dish})-[:hasIngredient]->(i:Ingredient)-[:ingredientCategory]->(c:IngredientCategory)
            RETURN d.name AS dish, c.name AS answer,
                   [
                     {subject:d.name, relation:'hasIngredient', target:i.name, target_type:'Ingredient'},
                     {subject:i.name, relation:'ingredientCategory', target:c.name, target_type:'IngredientCategory'}
                   ] AS triples,
                   'IngredientCategory' AS answer_label,
                   i.name AS anchor
        """,
        "allergen_restrictions": """
            MATCH (d:Dish {name:$dish})-[:hasIngredient]->(i:Ingredient)-[:hasAllergen]->(a:Allergen)
            RETURN d.name AS dish, a.name AS answer,
                   [
                     {subject:d.name, relation:'hasIngredient', target:i.name, target_type:'Ingredient'},
                     {subject:i.name, relation:'hasAllergen', target:a.name, target_type:'Allergen'}
                   ] AS triples,
                   'Allergen' AS answer_label,
                   i.name AS anchor
        """,
        "dietary_restrictions": """
            MATCH (d:Dish {name:$dish})-[:hasIngredient]->(i:Ingredient)-[:hasDietaryTag]->(t:DietaryTag)
            RETURN d.name AS dish, t.name AS answer,
                   [
                     {subject:d.name, relation:'hasIngredient', target:i.name, target_type:'Ingredient'},
                     {subject:i.name, relation:'hasDietaryTag', target:t.name, target_type:'DietaryTag'}
                   ] AS triples,
                   'DietaryTag' AS answer_label,
                   i.name AS anchor
        """,
        "ingredient_substitutions": """
            MATCH (d:Dish {name:$dish})-[:hasSubRule]->(sr:SubstitutionRule)-[:fromIngredient]->(src:Ingredient)
            MATCH (sr)-[:toIngredient]->(dst:Ingredient)
            RETURN d.name AS dish, dst.name AS answer,
                   [
                     {subject:d.name, relation:'hasSubRule', target:sr.name, target_type:'SubstitutionRule'},
                     {subject:sr.name, relation:'fromIngredient', target:src.name, target_type:'Ingredient'},
                     {subject:sr.name, relation:'toIngredient', target:dst.name, target_type:'Ingredient'}
                   ] AS triples,
                   'Ingredient' AS answer_label,
                   src.name AS anchor
        """,
    }

    query = query_map.get(qtype)
    if not query:
        return []

    with driver.session() as session:
        rows = list(session.run(query, dish=dish))

    for row in rows:
        anchor = row["anchor"]
        priority = 0 if slug(anchor) in visible_set else 1
        candidates.append(
            {
                "dish": row["dish"],
                "answer": row["answer"],
                "answer_label": row["answer_label"],
                "triples": row["triples"],
                "anchor": anchor,
                "priority": priority,
            }
        )

    candidates.sort(key=lambda x: (x["priority"], x["anchor"], x["answer"]))
    return candidates


# ---------------------------------------------------------------------------
# LLM generation
# ---------------------------------------------------------------------------

def verbalize_triples(triples: list[dict[str, str]]) -> list[str]:
    result = []
    for t in triples:
        subj = t.get("subject", "")
        rel = t.get("relation", "")
        tgt = t.get("target", "")
        result.append(f"{subj} ; {RELATION_VI.get(rel, rel)} ; {tgt}")
    return result


def build_choices(correct: str, distractors: list[str], rng: random.Random) -> tuple[dict[str, str], str]:
    options = [correct] + distractors[:3]
    while len(options) < 4:
        filler = f"Phương án {len(options) + 1}"
        if filler not in options:
            options.append(filler)
    rng.shuffle(options)
    letters = ["A", "B", "C", "D"]
    choices = {letter: text for letter, text in zip(letters, options, strict=True)}
    answer_letter = next(letter for letter, text in choices.items() if text == correct)
    return choices, answer_letter


def call_gemini_generate(client, payload: dict[str, Any], retries: int = 3) -> dict[str, Any] | None:
    for attempt in range(1, retries + 1):
        try:
            resp = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=GENERATION_PROMPT + "\n\n" + json.dumps(payload, ensure_ascii=False, indent=2),
                config={
                    "temperature": 0.35,
                    "max_output_tokens": 2048,
                    "response_mime_type": "application/json",
                },
            )
            raw = resp.text.strip()
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
        except Exception as exc:  # noqa: BLE001
            print(f"    Gemini attempt {attempt} failed: {type(exc).__name__}: {exc}")
        time.sleep(1.5 * attempt)
    return None


def validate_generation(result: dict[str, Any], expected_choices: dict[str, str], expected_answer: str) -> bool:
    if not result or result.get("skip") is True:
        return False
    if set((result.get("choices") or {}).keys()) != {"A", "B", "C", "D"}:
        return False
    if result.get("choices") != expected_choices:
        return False
    if result.get("answer") != expected_answer:
        return False
    if not norm_text(result.get("question_vi", "")):
        return False
    if not norm_text(result.get("rationale_vi", "")):
        return False
    return True


# ---------------------------------------------------------------------------
# Sample generation
# ---------------------------------------------------------------------------

def make_generation_payload(
    image_row: dict[str, Any],
    dish: str,
    qtype: str,
    candidate: dict[str, Any],
    choices: dict[str, str],
    answer_letter: str,
) -> dict[str, Any]:
    return {
        "image_context": {
            "image_id": image_row.get("image_id") or image_row.get("id") or image_row.get("uuid"),
            "image": image_row.get("image_url") or image_row.get("image_file") or image_row.get("image_path"),
            "dish": dish,
            "food_items": image_row.get("food_items", []),
            "image_description": image_row.get("image_description") or image_row.get("image_desc") or image_row.get("description") or image_row.get("caption"),
        },
        "question_type": qtype,
        "anchor_entity": candidate.get("anchor"),
        "retrieved_triples": verbalize_triples(candidate["triples"]),
        "fixed_choices": choices,
        "correct_answer_letter": answer_letter,
        "correct_answer_text": candidate["answer"],
        "generation_constraints": {
            "must_require_external_knowledge": True,
            "must_be_grounded_in_visual_context": True,
            "language": "vi",
            "mcq_4": True,
        },
    }


def generate_one_sample(
    gemini_client,
    driver,
    rng: random.Random,
    image_row: dict[str, Any],
    dish: str,
    qtype: str,
) -> dict[str, Any] | None:
    candidates = retrieve_fact_candidates(driver, dish, qtype, image_row["food_items"])
    if not candidates:
        return None

    candidate = candidates[0]
    distractors = get_distractors(driver, candidate["answer_label"], exclude=[candidate["answer"]], limit=8)
    distractors = [d for d in distractors if d != candidate["answer"]][:3]
    if len(distractors) < 3:
        return None

    choices, answer_letter = build_choices(candidate["answer"], distractors, rng)
    payload = make_generation_payload(image_row, dish, qtype, candidate, choices, answer_letter)
    llm_result = call_gemini_generate(gemini_client, payload)
    if not validate_generation(llm_result or {}, choices, answer_letter):
        return None

    return {
        "image_id": image_row.get("image_id") or image_row.get("id") or image_row.get("uuid"),
        "image": image_row.get("image_url") or image_row.get("image_file") or image_row.get("image_path"),
        "dish": dish,
        "qtype": qtype,
        "question_vi": llm_result["question_vi"],
        "choices": llm_result["choices"],
        "answer": llm_result["answer"],
        "answer_text": llm_result["choices"][llm_result["answer"]],
        "rationale_vi": llm_result["rationale_vi"],
        "triples_used": candidate["triples"],
        "retrieved_triples_text": verbalize_triples(candidate["triples"]),
        "food_items": image_row["food_items"],
        "image_description": image_row["image_description"],
        "anchor_entity": candidate["anchor"],
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate ViFoodVQA samples from KG + image metadata")
    parser.add_argument("--table", default="image")
    parser.add_argument("--id-col", default="image_id")
    parser.add_argument("--image-col", default="image_url")
    parser.add_argument("--desc-col", default="image_desc")
    parser.add_argument("--items-col", default="food_items")
    parser.add_argument("--question-types-csv", default=str(QUESTION_TYPES_FILE))
    parser.add_argument("--limit-images", type=int, default=50)
    parser.add_argument("--start-page", type=int, default=-1)
    parser.add_argument("--qtypes-per-image", type=int, default=2)
    parser.add_argument("--qtypes", nargs="*", default=[])
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rng = random.Random(args.seed)

    requested_qtypes = []
    if args.qtypes:
        for raw in args.qtypes:
            canon = SUPPORTED_QTYPE_ALIASES.get(norm_text(raw).lower(), norm_text(raw).lower())
            if canon not in UNSUPPORTED_QTYPES:
                requested_qtypes.append(canon)
    else:
        requested_qtypes = load_question_types_csv(Path(args.question_types_csv))

    if not requested_qtypes:
        print("No supported question types selected.")
        sys.exit(1)

    progress = load_progress()
    if args.start_page >= 0:
        progress["page"] = args.start_page

    seen_keys = set(progress.get("seen_keys", []))
    generated = progress.get("generated", [])

    supabase = make_supabase_client()
    driver = make_neo4j_driver()
    gemini_client = make_gemini_client()
    dish_aliases = fetch_dish_aliases(driver)

    print(f"Loaded {len(dish_aliases)} dish names from Neo4j")
    print(f"Question types: {', '.join(requested_qtypes)}")

    page = progress["page"]
    total_attempted_images = 0

    try:
        while len(generated) < args.limit_images:
            rows = fetch_image_rows(
                supabase,
                args.table,
                args.id_col,
                args.image_col,
                args.desc_col,
                args.items_col,
                page,
                PAGE_SIZE,
            )
            if not rows:
                break

            print(f"\nPage {page}: {len(rows)} image rows")
            for raw in rows:
                if len(generated) >= args.limit_images:
                    break

                image_row = {
                    "image_id": raw.get(args.id_col),
                    "image_url": raw.get(args.image_col),
                    "image_description": norm_text(raw.get(args.desc_col, "")),
                    "food_items": [norm_text(x) for x in (raw.get(args.items_col) or []) if norm_text(x)],
                }
                total_attempted_images += 1

                if not image_row["food_items"] or not image_row["image_description"]:
                    continue

                dish = choose_main_dish(image_row["food_items"], dish_aliases)
                if not dish:
                    continue

                shuffled_qtypes = requested_qtypes[:]
                rng.shuffle(shuffled_qtypes)
                picked = 0

                for qtype in shuffled_qtypes:
                    if picked >= args.qtypes_per_image or len(generated) >= args.limit_images:
                        break
                    sample_key = f"{image_row['image_id']}::{qtype}"
                    if sample_key in seen_keys:
                        continue

                    sample = generate_one_sample(gemini_client, driver, rng, image_row, dish, qtype)
                    if not sample:
                        continue

                    generated.append(sample)
                    seen_keys.add(sample_key)
                    picked += 1
                    print(f"  ✓ {sample_key} -> {sample['answer']} | {sample['question_vi'][:90]}")

                    progress = {
                        "page": page,
                        "generated": generated,
                        "seen_keys": sorted(seen_keys),
                    }
                    save_progress(progress)

            page += 1
            progress["page"] = page
            save_progress(progress)

    finally:
        driver.close()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(generated, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n-- Done --")
    print(f"Attempted images: {total_attempted_images}")
    print(f"Generated samples: {len(generated)}")
    print(f"Saved: {OUTPUT_FILE}")
    print(f"Checkpoint: {PROGRESS_FILE}")


if __name__ == "__main__":
    main()
