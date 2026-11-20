"""Compare a completed frozen dense run with development-only screening controls."""

import argparse
from pathlib import Path

from adaptive_astc.data.unity_tile_archive import UnityTileArchive
from adaptive_astc.evaluation.unity_dense_screening import UnityDenseScreening
from adaptive_astc.utils.artifacts import ArtifactStore as A

ROOT = Path(__file__).resolve().parents[1]
HANDOFF = ROOT / "experiment report/unity-accuracy90-20261111"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-run", type=Path, required=True)
    parser.add_argument("--step-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / "experiment report/.local/unity-v5-20261119"):
        parser.error("Keep V5 raw results in its local experiment directory")
    archive = UnityTileArchive(HANDOFF / "unity-v2-data-inputs.json")
    training = args.training_run / "report.json"
    run = A.read_json(training)
    if run["status"] != "passed" or run["test_opened"] is not False:
        raise ValueError("Expected a completed development-only dense run")
    rows_path = args.training_run / "best-validation.json"
    dense = archive.read_bound_json(rows_path, run["best_validation_sha256"], dict)
    step = A.read_json(args.step_report)
    if (
        step["status"] != "passed"
        or step["split"] != "validation"
        or step["test_opened"] is not False
        or step["candidate"] != [8, "fastest"]
        or step["development_corpus_sha256"] != archive.sha256
    ):
        raise ValueError("Expected matched 8x8 fastest step baseline on development data")
    policy = HANDOFF / "unity-development-corpus11000-v2-interface.json"
    results = UnityDenseScreening(archive, policy).compare(dense["images"], step["rows"])
    result = {
        "status": "passed",
        "stage": run["stage"],
        "test_opened": False,
        "training_report_sha256": A.sha256_file(training),
        "validation_sha256": run["best_validation_sha256"],
        "step_report_sha256": A.sha256_file(args.step_report),
        "source_sha256": A.sha256_file(
            ROOT / "src/adaptive_astc/evaluation/unity_dense_screening.py"
        ),
        **results,
    }
    output.mkdir(parents=True, exist_ok=False)
    A.write_json(output / "report.json", result)
    print(f"Compared four screening rankings on {result['images']} matched color images")


if __name__ == "__main__":
    main()
