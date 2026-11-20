"""Bind the six approved V5 pixel-overlap replacements to the frozen reserve order."""

import argparse
import sys
from pathlib import Path

from PIL import Image

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline.confirmation_capture import UnityConfirmationCapture
from reproductions.unity_search_baseline.confirmation_series import UnityConfirmationSeries
from script.prepare_unity_v5_confirmation_capture import (
    EXECUTION,
    PUBLIC,
    ROOT,
    checked,
    record,
    unsupported_import,
)
from script.reserve_unity_v5_confirmation import verify_reservation

REVISION = EXECUTION / "pixel-overlap-revision-v2"
PREFLIGHT = PUBLIC / "confirmation-pixel-revision-preflight-v2.json"
COLLECTION = PUBLIC / "confirmation-replacement-capture-v2.json"
RUN_ID = "unity-v5-confirmation1000-pixel-replacements-v2"
REVISED_CAPTURE = PUBLIC / "confirmation-complete-capture-v2.json"
REVISED_AUDIT = PUBLIC / "confirmation-pixel-isolation-v2.json"
STATUS = PUBLIC / "confirmation-execution-v2.json"


def replace_overlaps(
    manifest: JsonDict, audit: JsonDict, project: Path, original_reserves: list[JsonDict]
) -> tuple[JsonDict, list[JsonDict], list[JsonDict]]:
    primary = list(manifest["primary"])
    reserves = list(manifest["reserves"])
    exact = {
        name
        for group in audit["exact_cross_cohort_groups"]
        for name in group["confirmation_assets"]
    }
    near = {
        name for group in audit["near_cross_cohort_groups"] for name in group["confirmation_assets"]
    }
    slots = [i for i, row in enumerate(primary) if row["path"] in exact | near]
    if slots != [229, 255, 272, 394, 592, 947] or len(exact | near) != 6:
        raise ValueError("Pixel overlaps do not match the six approved primary positions")
    order = {row["path"]: i for i, row in enumerate(original_reserves)}
    if [order[row["path"]] for row in reserves] != sorted(order[row["path"]] for row in reserves):
        raise ValueError("Remaining reserve order changed")
    eligible = (row for row in reserves if unsupported_import(project, row) is None)
    replacements, changes = [], []
    for i in slots:
        selected = next(eligible)
        path = project / selected["path"]
        if A.sha256_file(path) != selected["source_sha256"]:
            raise ValueError("Approved reserve source changed")
        with Image.open(path) as image:
            image.load()
        original = primary[i]["path"]
        changes.append(
            {
                "primary_index": i,
                "excluded_path": original,
                "reason": "exact_rgba" if original in exact else "near_rgba",
                "original_reserve_index": order[selected["path"]],
                "replacement_path": selected["path"],
            }
        )
        replacements.append(selected)
        primary[i] = selected
    used = {row["path"] for row in replacements}
    revised = {key: value for key, value in manifest.items() if key != "fingerprint"}
    revised.update(
        primary=primary,
        reserves=[row for row in reserves if row["path"] not in used],
        approved_pixel_replacements=changes,
    )
    return revised, replacements, changes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approve-six-pixel-replacements", action="store_true", required=True)
    parser.parse_args()
    status_path = PUBLIC / "confirmation-execution-recovered-v1.json"
    previous = A.read_json(status_path)
    prior_audit = checked(previous["pixel_audit_result"])
    audit = A.read_json(prior_audit)
    if (
        previous["status"] != "stopped_pixel_overlap"
        or previous["formal_evaluation_started"] is not False
        or audit["test_opened"] is not False
        or audit["status"] != "failed_cross_cohort_overlap"
        or audit["counts"] != {"train": 10000, "validation": 1000, "confirmation": 1000}
    ):
        raise ValueError("Expected the unopened cohort and its completed failed isolation audit")
    old_preflight = A.read_json(checked(audit["execution_preflight"]))
    protocol_path = checked(old_preflight["protocol"])
    protocol = A.read_json(protocol_path)
    checked(protocol["model"])
    checked(protocol["native_policy_model"])
    old_capture = checked(previous["completed_capture"])
    if checked(audit["series_report"]).resolve() != old_capture.resolve():
        raise ValueError("Failed audit and capture refer to different cohorts")
    old_summary = A.read_json(checked(old_preflight["revised_reservation"]))
    prior_manifest = checked(
        {"path": old_summary["manifest"], "sha256": old_summary["manifest_sha256"]}
    )
    manifest = A.read_json(prior_manifest)
    config = A.read_json(EXECUTION / "smoke-config.json")
    source_config = A.read_json(checked(config["reservation_config"]))
    project = Path(source_config["image_root"]).resolve()
    orig = A.read_json(checked(protocol["source_manifest"]))
    revised, replacements, changes = replace_overlaps(manifest, audit, project, orig["reserves"])
    revised["prior_manifest_sha256"] = A.sha256_file(prior_manifest)
    revised["selection_basis"] = "Input isolation only, before reading any confirmation predictions"
    revised["fingerprint"] = A.fingerprint(revised)
    REVISION.mkdir(parents=True, exist_ok=False)
    manifest_path = REVISION / "revised-manifest.json"
    A.write_json(manifest_path, revised)
    summary = old_summary | {
        "manifest": str(manifest_path),
        "manifest_sha256": A.sha256_file(manifest_path),
        "primary_groups": len({row["group"] for row in revised["primary"]}),
        "reserve_images": len(revised["reserves"]),
        "approved_pixel_replacements": changes,
    }
    source_isolation = REVISION / "source-isolation.json"
    A.write_json(source_isolation, verify_reservation(summary, source_config))
    subset = {
        "status": "reserved",
        "primary": replacements,
        "reserves": [],
        "test_opened": False,
        "config_sha256": summary["config_sha256"],
        "parent_manifest_sha256": summary["manifest_sha256"],
    }
    subset["fingerprint"] = A.fingerprint(subset)
    subset_path = REVISION / "six-imports.json"
    A.write_json(subset_path, subset)
    reservation = REVISION / "six-reservation.json"
    A.write_json(
        reservation,
        {
            "status": "reserved",
            "manifest": str(subset_path),
            "manifest_sha256": A.sha256_file(subset_path),
            "config_sha256": summary["config_sha256"],
            "primary_images": 6,
        },
    )
    smoke = REVISION / "smoke-config.json"
    A.write_json(
        smoke,
        config
        | {
            "reservation_report": record(reservation),
            "start": 0,
            "images": 2,
            "run_id": f"{RUN_ID}-smoke2",
            "report": str(PUBLIC / f"{RUN_ID}-smoke2.json"),
        },
    )
    job = REVISION / "smoke-job/config.json"
    A.write_json(
        job,
        {
            "command": [
                sys.executable,
                "-u",
                "script/capture_unity_confirmation.py",
                "--config",
                str(smoke),
            ],
            "scope": "First two of the six approved V5 pixel-isolation replacements",
        },
    )
    series = REVISION / "series-config.json"
    A.write_json(
        series,
        {
            "smoke_config": record(smoke),
            "smoke_job": {"job_config": str(job), "sha256": A.sha256_file(job)},
            "sources_sha256": UnityConfirmationSeries.execution_sources(ROOT),
            "expected_images": 6,
            "batch_size": 4,
            "run_id": RUN_ID,
            "report": str(COLLECTION),
        },
    )
    UnityConfirmationCapture(ROOT, smoke).validate()
    UnityConfirmationSeries(ROOT, series).validate()
    A.write_json(
        PREFLIGHT,
        {
            "status": "approved_six_replacements_ready_for_capture",
            "prior_failed_audit": record(prior_audit),
            "prior_completed_capture": record(old_capture),
            "prior_execution_authorization": record(checked(audit["execution_preflight"])),
            "prior_manifest": record(prior_manifest),
            "protocol": record(protocol_path),
            "revised_manifest": record(manifest_path),
            "source_isolation": record(source_isolation),
            "replacement_subset": record(subset_path),
            "approved_pixel_replacements": changes,
            "smoke_job": record(job),
            "replacement_series_configuration": record(series),
            "confirmation_authorized_by_user": True,
            "model_evaluation_requires_full_pixel_isolation_pass": True,
        },
    )
    print(f"Approved six replacement positions bound: {PREFLIGHT}")


if __name__ == "__main__":
    main()
