"""Prepare the approved V5 cohort revision and native capture job configurations."""

import argparse
import re
import sys
from pathlib import Path

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline.confirmation_capture import UnityConfirmationCapture
from reproductions.unity_search_baseline.confirmation_series import UnityConfirmationSeries
from reproductions.unity_search_baseline.native_data_pipeline import UnityNativeDataPipeline
from script.reserve_unity_v5_confirmation import verify_reservation

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "experiment report/unity-v5-20261119"
RAW = ROOT / "experiment report/.local/unity-v5-20261119"
HISTORICAL = ROOT / "experiment report/unity-accuracy90-20261111"
RUN_ID = "unity-v5-confirmation1000-v1"
EXECUTION = RAW / "confirmation-execution1000-v1"


def record(path: Path) -> JsonDict:
    return {"path": str(path.resolve()), "sha256": A.sha256_file(path)}


def checked(binding: JsonDict) -> Path:
    path = ROOT / binding["path"]
    if A.sha256_file(path) != binding["sha256"]:
        raise ValueError(f"Frozen confirmation artifact changed: {path}")
    return path


def unsupported_import(project: Path, row: JsonDict) -> str | None:
    asset = (project / row["path"]).resolve()
    if not asset.is_relative_to(project / "Assets"):
        raise ValueError("Reserved asset is outside the Unity project")
    meta = Path(str(asset) + ".meta")
    if A.sha256_file(meta) != row["meta_sha256"]:
        raise ValueError(f"Reserved Unity metadata changed: {asset}")
    text = meta.read_text(encoding="utf-8-sig")
    if re.search(r"(?m)^ +textureShape:[ \t]*2[ \t]*$", text):
        return "Cube"
    if re.search(r"(?m)^ +textureType:[ \t]*2[ \t]*$", text):
        return "GUI"
    if asset.suffix.lower() in {".hdr", ".exr"}:
        return "HDR"
    return None


def revise(archive: JsonDict, project: Path, original_sha256: str) -> JsonDict:
    primary = list(archive["primary"])
    reserves = list(archive["reserves"])
    if len(primary) != 1000 or len(reserves) != 250 or archive["test_opened"] is not False:
        raise ValueError("Expected the unopened frozen V5 cohort")
    exclusions = {
        index: reason
        for index, row in enumerate(primary)
        if (reason := unsupported_import(project, row)) is not None
    }
    if exclusions != {313: "GUI", 458: "Cube"}:
        raise ValueError(f"The source issues differ from the two approved exclusions: {exclusions}")
    available = (
        (index, row)
        for index, row in enumerate(reserves)
        if unsupported_import(project, row) is None
    )
    replacements = []
    used = set()
    for index, reason in exclusions.items():
        source_index, replacement = next(available)
        used.add(source_index)
        replacements.append(
            {
                "primary_index": index,
                "excluded_path": primary[index]["path"],
                "reason": reason,
                "original_reserve_index": source_index,
                "replacement_path": replacement["path"],
            }
        )
        primary[index] = replacement
    revised = {key: value for key, value in archive.items() if key != "fingerprint"}
    revised.update(
        primary=primary,
        reserves=[row for index, row in enumerate(reserves) if index not in used],
        original_manifest_sha256=original_sha256,
        approved_import_replacements=replacements,
    )
    revised["fingerprint"] = A.fingerprint(revised)
    return revised


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approve-import-replacements", action="store_true", required=True)
    parser.parse_args()
    progress = A.read_json(PUBLIC / "progress.json")
    protocol_path = checked(progress["confirmation_protocol"])
    protocol = A.read_json(protocol_path)
    if (
        protocol["confirmation_opened"] is not False
        or protocol["screening_rule"]
        != {
            "view": "display",
            "region": "content",
            "y_db": 28,
            "x_share": 0.1,
        }
        or protocol["screening_candidate"] != [8, "fastest"]
    ):
        raise ValueError("Expected the unopened 28 dB / 10% V5 protocol")
    for name in ("model", "native_policy_model", "training_report", "source_isolation"):
        checked(protocol[name])
    for binding in protocol["human_rating_inputs"].values():
        checked(binding)
    for name, digest in protocol["source_sha256"].items():
        checked({"path": name, "sha256": digest})
    manifest = checked(protocol["source_manifest"])
    config_path = RAW / "confirmation-source1000-reserve250-v1-configuration/config.json"
    reservation_path = PUBLIC / "confirmation-source1000-reserve250-v1.json"
    reservation = A.read_json(reservation_path)
    config = A.read_json(config_path)
    if (
        reservation["manifest_sha256"] != protocol["source_manifest"]["sha256"]
        or Path(reservation["manifest"]).resolve() != manifest.resolve()
        or reservation["config_sha256"] != A.sha256_file(config_path)
    ):
        raise ValueError("Original V5 source reservation does not match the frozen protocol")
    project = Path(config["image_root"]).resolve()
    revised = revise(A.read_json(manifest), project, reservation["manifest_sha256"])
    EXECUTION.mkdir(parents=True, exist_ok=False)
    revised_path = EXECUTION / "manifest.json"
    A.write_json(revised_path, revised)
    revised_summary = reservation | {
        "manifest": str(revised_path),
        "manifest_sha256": A.sha256_file(revised_path),
        "reserve_images": len(revised["reserves"]),
        "primary_groups": len({row["group"] for row in revised["primary"]}),
        "approved_import_replacements": revised["approved_import_replacements"],
    }
    revised_report = EXECUTION / "reservation.json"
    A.write_json(revised_report, revised_summary)
    isolation = verify_reservation(revised_summary, config)
    source_receipt = EXECUTION / "source-isolation.json"
    A.write_json(source_receipt, isolation)

    historical = A.read_json(HISTORICAL / "unity-confirmation-capture-smoke2-v2-config.json")
    dev = historical["development_series"]
    checked(dev)
    dependencies = [historical["dependencies"][0]]
    for name in ("labels-full-v1", "dense-joint-full-v1"):
        path = RAW / "jobs" / name / "config.json"
        dependencies.append({"job_config": str(path), "sha256": A.sha256_file(path)})
    for dependency in dependencies:
        if UnityNativeDataPipeline.dependency_status(dependency)["status"] != "passed":
            raise ValueError("V5 capture requires terminal, successful development jobs")

    capture_config = EXECUTION / "smoke-config.json"
    capture_report = PUBLIC / f"{RUN_ID}-smoke2.json"
    smoke_id = f"{RUN_ID}-smoke2"
    A.write_json(
        capture_config,
        {
            "reservation_report": record(revised_report),
            "reservation_config": record(config_path),
            "development_series": dev,
            "sources_sha256": UnityConfirmationCapture.execution_sources(ROOT),
            "dependencies": dependencies,
            "start": 0,
            "images": 2,
            "run_id": smoke_id,
            "report": str(capture_report),
            "minimum_free_ram_gib": historical["minimum_free_ram_gib"],
            "minimum_free_disk_gib": historical["minimum_free_disk_gib"],
        },
    )
    smoke_job = EXECUTION / "smoke-job/config.json"
    A.write_json(
        smoke_job,
        {
            "command": [
                sys.executable,
                "-u",
                "script/capture_unity_confirmation.py",
                "--config",
                str(capture_config.resolve()),
            ],
            "scope": "First two unchanged primary V5 imports with no model inference",
        },
    )
    series_config = EXECUTION / "series-config.json"
    series_report = PUBLIC / f"{RUN_ID}-series.json"
    A.write_json(
        series_config,
        {
            "smoke_config": record(capture_config),
            "smoke_job": {"job_config": str(smoke_job), "sha256": A.sha256_file(smoke_job)},
            "sources_sha256": UnityConfirmationSeries.execution_sources(ROOT),
            "expected_images": 1000,
            "batch_size": 256,
            "run_id": RUN_ID,
            "report": str(series_report),
        },
    )
    smoke = UnityConfirmationCapture(ROOT, capture_config).validate()
    series = UnityConfirmationSeries(ROOT, series_config).validate()
    report = PUBLIC / "confirmation-execution-preflight-v1.json"
    if report.exists():
        raise FileExistsError("Preserve the prior V5 execution preflight")
    A.write_json(
        report,
        {
            "status": "source_revision_and_capture_plan_validated",
            "protocol": record(protocol_path),
            "revised_reservation": record(revised_report),
            "revised_source_isolation": record(source_receipt),
            "approved_import_replacements": revised["approved_import_replacements"],
            "smoke_job": record(smoke_job),
            "smoke_validation": smoke,
            "series_configuration": record(series_config),
            "series_validation": series,
            "screening_rule": protocol["screening_rule"],
            "confirmation_authorized_by_user": True,
            "model_evaluation_requires_full_pixel_isolation_pass": True,
        },
    )
    print(f"V5 execution preflight: {report}")


if __name__ == "__main__":
    main()
