from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


def load_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path).resolve()
    with config_path.open("r", encoding="utf-8") as f:
        loaded = yaml.safe_load(f) or {}

    cfg = _with_defaults(loaded)
    cfg["_config_path"] = str(config_path)
    cfg["_eval_root"] = str(config_path.parent.parent)
    cfg["_project_root"] = str(config_path.parent.parent.parent)
    load_dotenv(config_path.parent.parent / ".env")
    return cfg


def eval_root(cfg: dict[str, Any]) -> Path:
    return Path(cfg["_eval_root"]).resolve()


def project_root(cfg: dict[str, Any]) -> Path:
    return Path(cfg["_project_root"]).resolve()


def resolve_eval_path(cfg: dict[str, Any], value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return eval_root(cfg) / path


def resolve_project_path(cfg: dict[str, Any], value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return project_root(cfg) / path


def selected_models(cfg: dict[str, Any], names: list[str] | None) -> dict[str, dict[str, Any]]:
    models = cfg.get("models", {})
    if not names:
        return models
    missing = [name for name in names if name not in models]
    if missing:
        raise KeyError(f"Unknown model(s): {', '.join(missing)}")
    return {name: models[name] for name in names}


def selected_conditions(cfg: dict[str, Any], names: list[str] | None) -> list[dict[str, Any]]:
    conditions = cfg["evaluation"]["conditions"]
    if not names:
        return conditions
    by_name = {condition["name"]: condition for condition in conditions}
    missing = [name for name in names if name not in by_name]
    if missing:
        raise KeyError(f"Unknown condition(s): {', '.join(missing)}")
    return [by_name[name] for name in names]


def _with_defaults(loaded: dict[str, Any]) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "dataset": {
            "repo_id": "hoangphann/ViFoodVQA",
            "revision": None,
            "data_dir": "data/vifoodvqa",
            "test_split": "test",
            "require_nonempty_triples": True,
        },
        "paths": {
            "output_dir": "outputs",
            "vqa_src_dir": "../ViFoodVQA/src",
            "kg_question_types_csv": "../config/question_types.csv",
        },
        "evaluation": {
            "seed": 42,
            "top_k": 10,
            "max_new_tokens": 256,
            "temperature": 0,
            "fixed_shot_vqa_ids": [153, 149],
            "conditions": [],
        },
        "models": {},
    }
    return _deep_merge(defaults, loaded)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result

