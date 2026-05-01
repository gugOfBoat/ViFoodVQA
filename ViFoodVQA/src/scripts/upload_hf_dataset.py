"""
Upload the ViFoodVQA Hugging Face export as raw JSONL plus one image store.

This script deliberately does not build `datasets.Dataset` objects. It uploads
the split JSONL files and `images/` directory directly so image bytes are stored
once instead of being embedded into every VQA row as Parquet shards.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from huggingface_hub import HfApi

DEFAULT_REPO_ID = "hoangphann/ViFoodVQA"
DEFAULT_HF_DIR = Path("hf_dataset")
DEFAULT_COMMIT_MESSAGE = "Upload ViFoodVQA JSONL dataset with single image store"

SPLITS = ("train", "validation", "test")
ALLOW_PATTERNS = [
    "README.md",
    ".gitattributes",
    "data/train.jsonl",
    "data/validation.jsonl",
    "data/test.jsonl",
    "images/**",
]
PARQUET_DELETE_PATTERNS = ["data/*.parquet"]
IMAGE_FEATURE_PATTERN = re.compile(
    r"(?ms)^\s*-\s+name:\s+image\s*$\s*^\s*dtype:\s*(?P<dtype>\w+)\s*$"
)


@dataclass(frozen=True)
class SplitStats:
    split: str
    rows: int
    unique_images: int


@dataclass(frozen=True)
class ExportStats:
    split_stats: list[SplitStats]
    unique_images: set[str]
    referenced_image_bytes: int
    image_file_count: int
    image_dir_bytes: int

    @property
    def total_rows(self) -> int:
        return sum(item.rows for item in self.split_stats)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Upload hf_dataset/ to Hugging Face as JSONL files plus a single "
            "images/ directory, without creating embedded-image Parquet shards."
        )
    )
    parser.add_argument(
        "--hf-dir",
        default=str(DEFAULT_HF_DIR),
        help="Local Hugging Face export directory. Default: hf_dataset",
    )
    parser.add_argument(
        "--repo-id",
        default=DEFAULT_REPO_ID,
        help=f"Hugging Face dataset repo id. Default: {DEFAULT_REPO_ID}",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the export and print the planned upload without pushing.",
    )
    parser.add_argument(
        "--create-pr",
        action="store_true",
        help="Create a Hub pull request instead of committing directly.",
    )
    parser.add_argument(
        "--no-delete-parquet",
        action="store_true",
        help="Do not delete existing remote data/*.parquet files during upload.",
    )
    parser.add_argument(
        "--commit-message",
        default=DEFAULT_COMMIT_MESSAGE,
        help="Commit message for the Hub upload.",
    )
    return parser.parse_args()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at {path}:{line_no}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"Expected object row at {path}:{line_no}")
            rows.append(row)
    return rows


def normalize_image_path(value: object, *, jsonl_path: Path, row_number: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Row {row_number} in {jsonl_path} has no image string")

    image = value.strip()
    if "\\" in image:
        raise ValueError(
            f"Row {row_number} in {jsonl_path} uses backslashes in image path: {image}"
        )
    if "://" in image:
        raise ValueError(
            f"Row {row_number} in {jsonl_path} must use a local image path: {image}"
        )

    posix_path = PurePosixPath(image)
    if posix_path.is_absolute():
        raise ValueError(
            f"Row {row_number} in {jsonl_path} has absolute image path: {image}"
        )
    if not posix_path.parts or posix_path.parts[0] != "images":
        raise ValueError(
            f"Row {row_number} in {jsonl_path} image must be under images/: {image}"
        )
    if any(part in {"", ".", ".."} for part in posix_path.parts):
        raise ValueError(
            f"Row {row_number} in {jsonl_path} has unsafe image path: {image}"
        )

    return str(posix_path)


def assert_relative_to(path: Path, parent: Path, *, label: str) -> None:
    try:
        path.relative_to(parent)
    except ValueError as exc:
        raise ValueError(f"{label} escapes {parent}: {path}") from exc


def validate_export(hf_dir: Path) -> ExportStats:
    hf_dir = hf_dir.resolve()
    data_dir = hf_dir / "data"
    image_dir = hf_dir / "images"
    readme_path = hf_dir / "README.md"

    if not hf_dir.is_dir():
        raise FileNotFoundError(f"Missing export directory: {hf_dir}")
    if not image_dir.is_dir():
        raise FileNotFoundError(f"Missing image directory: {image_dir}")
    if not readme_path.is_file():
        raise FileNotFoundError(f"Missing dataset card: {readme_path}")
    validate_dataset_card(readme_path)

    split_stats: list[SplitStats] = []
    all_images: set[str] = set()
    image_dir_resolved = image_dir.resolve()

    for split in SPLITS:
        jsonl_path = data_dir / f"{split}.jsonl"
        if not jsonl_path.is_file():
            raise FileNotFoundError(f"Missing split file: {jsonl_path}")

        rows = load_jsonl(jsonl_path)
        split_images: set[str] = set()
        for index, row in enumerate(rows, start=1):
            image = normalize_image_path(
                row.get("image"),
                jsonl_path=jsonl_path,
                row_number=index,
            )
            local_image_path = (hf_dir / Path(*PurePosixPath(image).parts)).resolve()
            assert_relative_to(
                local_image_path,
                image_dir_resolved,
                label=f"Image path for row {index} in {jsonl_path}",
            )
            if not local_image_path.is_file():
                raise FileNotFoundError(
                    f"Missing image for row {index} in {jsonl_path}: {local_image_path}"
                )
            split_images.add(image)
            all_images.add(image)

        split_stats.append(
            SplitStats(split=split, rows=len(rows), unique_images=len(split_images))
        )

    referenced_image_bytes = sum(
        (hf_dir / Path(*PurePosixPath(image).parts)).stat().st_size
        for image in all_images
    )
    image_files = [path for path in image_dir.rglob("*") if path.is_file()]
    image_dir_bytes = sum(path.stat().st_size for path in image_files)

    return ExportStats(
        split_stats=split_stats,
        unique_images=all_images,
        referenced_image_bytes=referenced_image_bytes,
        image_file_count=len(image_files),
        image_dir_bytes=image_dir_bytes,
    )


def validate_dataset_card(readme_path: Path) -> None:
    text = readme_path.read_text(encoding="utf-8")
    match = IMAGE_FEATURE_PATTERN.search(text)
    if not match:
        return

    dtype = match.group("dtype").strip().lower()
    if dtype == "image":
        raise ValueError(
            f"{readme_path} declares image as dtype: image, but this export stores "
            "relative image paths in JSONL. Use dtype: string to keep the Hub "
            "streaming viewer from opening images/... inside its worker filesystem."
        )


def format_gib(size_bytes: int) -> str:
    return f"{size_bytes / (1024 ** 3):.3f} GiB"


def print_plan(
    *,
    hf_dir: Path,
    repo_id: str,
    stats: ExportStats,
    delete_patterns: list[str] | None,
    create_pr: bool,
    dry_run: bool,
) -> None:
    print("Validated local export:")
    print(f"  hf_dir: {hf_dir.resolve()}")
    for item in stats.split_stats:
        print(
            f"  {item.split}: {item.rows:,} rows, "
            f"{item.unique_images:,} unique referenced images"
        )
    print(f"  total rows: {stats.total_rows:,}")
    print(f"  unique referenced images: {len(stats.unique_images):,}")
    print(f"  referenced image size: {format_gib(stats.referenced_image_bytes)}")
    print(
        f"  images/ directory: {stats.image_file_count:,} files, "
        f"{format_gib(stats.image_dir_bytes)}"
    )

    print("\nUpload plan:")
    print(f"  repo_id: {repo_id}")
    print(f"  create_pr: {create_pr}")
    print(f"  allow_patterns: {', '.join(ALLOW_PATTERNS)}")
    if delete_patterns:
        print(f"  delete_patterns: {', '.join(delete_patterns)}")
    else:
        print("  delete_patterns: none")
    if dry_run:
        print("\nDry run only; no files were uploaded.")


def upload_export(
    *,
    hf_dir: Path,
    repo_id: str,
    delete_patterns: list[str] | None,
    create_pr: bool,
    commit_message: str,
) -> None:
    api = HfApi()
    commit_info = api.upload_folder(
        repo_id=repo_id,
        repo_type="dataset",
        folder_path=hf_dir,
        allow_patterns=ALLOW_PATTERNS,
        delete_patterns=delete_patterns,
        create_pr=create_pr,
        commit_message=commit_message,
    )
    print(f"\nDone: {commit_info.commit_url}")


def main() -> None:
    args = parse_args()
    hf_dir = Path(args.hf_dir).expanduser()
    delete_patterns = None if args.no_delete_parquet else PARQUET_DELETE_PATTERNS

    stats = validate_export(hf_dir)
    print_plan(
        hf_dir=hf_dir,
        repo_id=args.repo_id,
        stats=stats,
        delete_patterns=delete_patterns,
        create_pr=args.create_pr,
        dry_run=args.dry_run,
    )

    if args.dry_run:
        return

    upload_export(
        hf_dir=hf_dir,
        repo_id=args.repo_id,
        delete_patterns=delete_patterns,
        create_pr=args.create_pr,
        commit_message=args.commit_message,
    )


if __name__ == "__main__":
    main()
