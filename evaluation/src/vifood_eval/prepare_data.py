from __future__ import annotations

import argparse

from .config import load_config
from .data import ensure_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare ViFoodVQA evaluation data.")
    parser.add_argument("--config", default="configs/eval.yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)
    data_dir = ensure_dataset(cfg)
    print(f"Dataset ready: {data_dir}")


if __name__ == "__main__":
    main()

