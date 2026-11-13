"""Evaluate validation-only system variants from frozen native predictions."""

from __future__ import annotations

import argparse
from pathlib import Path

from reproductions.unity_search_baseline.system_variants import UnitySystemVariants


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    result = UnitySystemVariants(args.config).run()
    print({"status": result["status"], "model_forward_calls": result["model_forward_calls"]})


if __name__ == "__main__":
    main()
