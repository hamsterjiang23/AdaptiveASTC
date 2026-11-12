"""Validate or collect a frozen confirmation slice without opening model evaluation."""

from __future__ import annotations

import argparse
from pathlib import Path

from reproductions.unity_search_baseline.confirmation_capture import UnityConfirmationCapture


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    capture = UnityConfirmationCapture(Path(__file__).resolve().parents[1], args.config)
    result = capture.validate() if args.validate_only else capture.run()
    print({key: result[key] for key in ["status", "images", "source_split", "test_opened"]})


if __name__ == "__main__":
    main()
