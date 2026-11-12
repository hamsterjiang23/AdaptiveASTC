"""Queue approved development reference capture after the active confirmation series."""

import argparse
from pathlib import Path

from reproductions.unity_search_baseline.development_capture_queue import (
    UnityDevelopmentCaptureQueue,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    result = UnityDevelopmentCaptureQueue(Path.cwd(), args.config).run()
    print({key: result[key] for key in ["status", "images", "wall_seconds"]})


if __name__ == "__main__":
    main()
