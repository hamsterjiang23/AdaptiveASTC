"""Capture the six approved replacements, re-audit all 1,000, and gate V5 evaluation."""

from __future__ import annotations

import sys
import time

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.common.jobs import ReproductionJob
from reproductions.unity_search_baseline.confirmation_series import UnityConfirmationSeries
from reproductions.unity_search_baseline.native_data_pipeline import UnityNativeDataPipeline
from script.prepare_unity_v5_confirmation_capture import ROOT, checked, record
from script.prepare_unity_v5_pixel_revision import (
    COLLECTION,
    PREFLIGHT,
    REVISED_AUDIT,
    REVISED_CAPTURE,
    REVISION,
    STATUS,
)


def load_capture(binding: JsonDict) -> tuple[JsonDict, JsonDict]:
    report = A.read_json(checked(binding))
    manifest = A.read_json(
        checked({"path": report["manifest"], "sha256": report["manifest_sha256"]})
    )
    fingerprint = manifest.pop("fingerprint")
    if (
        fingerprint != A.fingerprint(manifest)
        or report["status"] != "passed"
        or manifest["status"] != "passed"
        or report["coverage"] != "complete"
        or manifest["test_opened"] is not False
        or manifest["batches"] != report["batches"]
    ):
        raise ValueError("Expected a complete unopened native capture")
    return report, manifest


def assemble(preflight: JsonDict) -> JsonDict:
    old, old_manifest = load_capture(preflight["prior_completed_capture"])
    small, small_manifest = load_capture(record(COLLECTION))
    revised = A.read_json(checked(preflight["revised_manifest"]))
    subset = A.read_json(checked(preflight["replacement_subset"]))
    old_rows = old_manifest["splits"]["confirmation"]
    replacements = small_manifest["splits"]["confirmation"]
    changes = preflight["approved_pixel_replacements"]
    if (
        len(old_rows) != 1000
        or len(replacements) != 6
        or len(changes) != 6
        or small_manifest["reservation_manifest_sha256"]
        != preflight["replacement_subset"]["sha256"]
        or old_manifest["reservation_manifest_sha256"] != preflight["prior_manifest"]["sha256"]
        or revised["approved_pixel_replacements"] != changes
        or [row["path"] for row in replacements] != [row["path"] for row in subset["primary"]]
    ):
        raise ValueError("Capture membership does not match the authorized revision")
    merged = list(old_rows)
    for change, row in zip(changes, replacements, strict=True):
        index = change["primary_index"]
        if (
            merged[index]["path"] != change["excluded_path"]
            or row["path"] != change["replacement_path"]
        ):
            raise ValueError("V5 replacement did not retain its approved position")
        merged[index] = row
    if any(
        actual["source_split"] != "confirmation"
        or actual["path"] != expected["path"]
        or actual["source_md4"] != expected["fileHash"]
        or any(actual[key] != expected[key] for key in ("source_sha256", "meta_sha256"))
        for actual, expected in zip(merged, revised["primary"], strict=True)
    ):
        raise ValueError("Merged Unity references differ from the approved primary order")
    batches = old["batches"] + small["batches"]
    manifest = {
        "status": "passed",
        "splits": {"confirmation": merged},
        "batches": batches,
        "reservation_manifest_sha256": preflight["revised_manifest"]["sha256"],
        "test_opened": False,
        "training_updates": 0,
    }
    manifest["fingerprint"] = A.fingerprint(manifest)
    manifest_path = REVISION / "complete-capture-manifest.json"
    if manifest_path.exists() or REVISED_CAPTURE.exists():
        raise FileExistsError("Preserve the prior revised assembly")
    A.write_json(manifest_path, manifest)
    report = {
        "status": "passed",
        "coverage": "complete",
        "captured_images": 1000,
        "reused_native_references": 994,
        "new_native_references": 6,
        "test_opened": False,
        "manifest": str(manifest_path),
        "manifest_sha256": A.sha256_file(manifest_path),
        "batches": batches,
        "revision_preflight": record(PREFLIGHT),
        "prior_completed_capture": preflight["prior_completed_capture"],
        "six_replacement_capture": record(COLLECTION),
    }
    A.write_json(REVISED_CAPTURE, report)
    return report


def job(name: str, script: str, *args: str) -> JsonDict:
    config = REVISION / f"{name}-job" / "config.json"
    if config.exists():
        raise FileExistsError("Preserve the prior V5 revision job")
    A.write_json(config, {"command": [sys.executable, "-u", script, *args], "scope": name})
    return ReproductionJob(ROOT, config).run()


def main() -> None:
    preflight = A.read_json(PREFLIGHT)
    if preflight["confirmation_authorized_by_user"] is not True:
        raise ValueError("The six replacement positions require user approval")
    frozen = checked(preflight["protocol"])
    checked(preflight["prior_failed_audit"])
    series_path = checked(preflight["replacement_series_configuration"])
    smoke_path = checked(preflight["smoke_job"])
    series = UnityConfirmationSeries(ROOT, series_path)
    if len(series.rows) != 6 or series.report != COLLECTION.resolve():
        raise ValueError("Only the six approved replacements may be re-imported")
    bound_sources = {
        name: A.sha256_file(ROOT / name)
        for name in (
            "script/run_unity_v5_pixel_revision.py",
            "script/audit_unity_v5_confirmation_pixels.py",
            "script/evaluate_unity_v5_confirmation.py",
            "script/prepare_unity_v5_pixel_revision.py",
        )
    }
    state: JsonDict = {
        "status": "running",
        "phase": "waiting_for_replacement_smoke",
        "revision_preflight": record(PREFLIGHT),
        "protocol": record(frozen),
        "approved_replacements": 6,
        "execution_sources": bound_sources,
        "formal_evaluation_started": False,
    }
    with STATUS.open("x", encoding="utf-8") as stream:
        stream.write("{}")
    started = time.perf_counter()
    try:
        A.write_json(STATUS, state)
        while True:
            smoke = UnityNativeDataPipeline.dependency_status(
                {
                    "job_config": str(smoke_path),
                    "sha256": preflight["smoke_job"]["sha256"],
                }
            )
            if smoke["status"] == "passed":
                break
            time.sleep(15)
        state["phase"] = "capture_remaining_four_replacements"
        A.write_json(STATUS, state)
        capture = job(
            "capture", "script/collect_unity_confirmation_series.py", "--config", str(series_path)
        )
        if capture["status"] != "passed":
            raise RuntimeError("Replacement Unity imports did not pass")
        checked(state["revision_preflight"])
        assemble(preflight)
        state.update(phase="audit_all_1000_pixels", capture=record(REVISED_CAPTURE))
        A.write_json(STATUS, state)
        for name, digest in bound_sources.items():
            checked({"path": name, "sha256": digest})
        audit = job(
            "pixel-audit",
            "script/audit_unity_v5_confirmation_pixels.py",
            "--revised-capture-sha256",
            state["capture"]["sha256"],
        )
        if REVISED_AUDIT.exists():
            state["pixel_audit"] = record(REVISED_AUDIT)
        if (
            audit["status"] != "passed"
            or A.read_json(REVISED_AUDIT)["full_scoped_pixel_isolation_passed"] is not True
        ):
            state["status"] = "stopped_pixel_isolation"
            raise RuntimeError("The full revised cohort did not pass pixel isolation")
        for name, digest in bound_sources.items():
            checked({"path": name, "sha256": digest})
        state.update(phase="formal_model_and_exact_psnr_evaluation", formal_evaluation_started=True)
        A.write_json(STATUS, state)
        result = job(
            "evaluation",
            "script/evaluate_unity_v5_confirmation.py",
            "--revised-cohort",
            "--pixel-gate-sha256",
            state["pixel_audit"]["sha256"],
        )
        if result["status"] != "passed":
            raise RuntimeError("Formal V5 evaluation failed; preserve its sealed attempt")
        from script.evaluate_unity_v5_confirmation import REPORT as EVALUATION

        state.update(
            status="machine_evaluation_complete_awaiting_independent_human_ratings",
            phase="blind_human_confirmation",
            evaluation=record(EVALUATION),
        )
    except BaseException as error:
        if state["status"] == "running":
            state["status"] = "stopped"
        state["error"] = repr(error)
        raise
    finally:
        state["wall_seconds"] = time.perf_counter() - started
        A.write_json(STATUS, state)


if __name__ == "__main__":
    main()
