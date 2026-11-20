"""Run authorized V5 capture, pixel audit, and evaluation in that order."""

from __future__ import annotations

import sys
import time

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_capture_input import UnityCaptureInputAdapter
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.common.jobs import ReproductionJob
from reproductions.unity_search_baseline.confirmation_series import UnityConfirmationSeries
from reproductions.unity_search_baseline.native_data_pipeline import UnityNativeDataPipeline
from script.audit_unity_v5_confirmation_pixels import REPORT as PIXEL_GATE
from script.evaluate_unity_v5_confirmation import REPORT as EVALUATION
from script.prepare_unity_v5_confirmation_capture import EXECUTION, PUBLIC, ROOT, checked, record

STATUS = PUBLIC / "confirmation-execution-v1.json"
PREFLIGHT = PUBLIC / "confirmation-execution-preflight-v1.json"


def phase_job(name: str, script: str, args: list[str]) -> JsonDict:
    config = EXECUTION / f"{name}-job" / "config.json"
    if config.exists():
        raise FileExistsError(f"Preserve the previous V5 {name} job")
    A.write_json(config, {"command": [sys.executable, "-u", script, *args], "scope": name})
    return ReproductionJob(ROOT, config).run()


def source_lock() -> dict[str, str]:
    names = (
        "script/run_unity_v5_confirmation.py",
        "script/audit_unity_v5_confirmation_pixels.py",
        "script/evaluate_unity_v5_confirmation.py",
        "script/prepare_unity_v5_confirmation_capture.py",
        "src/adaptive_astc/data/unity_capture_input.py",
        "src/adaptive_astc/utils/unity_evaluation_seal.py",
        "reproductions/unity_search_baseline/capture_policy.py",
        "reproductions/unity_search_baseline/near_duplicates.py",
        "reproductions/unity_search_baseline/supplement.py",
        "reproductions/unity_search_baseline/v3_deployment.py",
        "reproductions/unity_search_baseline/quality.py",
    )
    return {name: A.sha256_file(ROOT / name) for name in names}


def main() -> None:
    preflight = A.read_json(PREFLIGHT)
    if preflight["confirmation_authorized_by_user"] is not True:
        raise ValueError("Expected the approved V5 confirmation preflight")
    protocol = checked(preflight["protocol"])
    series_path = checked(preflight["series_configuration"])
    smoke_job = checked(preflight["smoke_job"])
    series = UnityConfirmationSeries(ROOT, series_path)
    execution_sources = source_lock()
    started = time.perf_counter()
    with STATUS.open("x", encoding="utf-8") as stream:
        stream.write("{}")
    state: JsonDict = {
        "status": "running",
        "phase": "waiting_for_two_native_imports",
        "images": 1000,
        "screening_rule": preflight["screening_rule"],
        "authorization_record": record(PREFLIGHT),
        "frozen_protocol": record(protocol),
        "execution_sources": execution_sources,
        "formal_evaluation_started": False,
    }
    try:
        A.write_json(STATUS, state)
        while True:
            dependency = UnityNativeDataPipeline.dependency_status(
                {
                    "job_config": str(smoke_job),
                    "sha256": preflight["smoke_job"]["sha256"],
                }
            )
            if dependency["status"] == "passed":
                break
            time.sleep(15)
        archive = series.smoke.baseline.run_dir / "references/normalized-batch/receipt.json"
        if not archive.is_file():
            raise ValueError("The initial Unity imports have no reference archive")
        inputs, smoke = series.audit_batch(series.smoke)
        UnityCaptureInputAdapter(inputs, "confirmation")
        state.update(phase="capture_all_native_inputs", smoke=smoke)
        A.write_json(STATUS, state)
        capture = phase_job(
            "capture", "script/collect_unity_confirmation_series.py", ["--config", str(series_path)]
        )
        if capture["status"] != "passed":
            raise RuntimeError(f"Full native capture stopped. See {series.report}")

        checked(state["authorization_record"])
        checked(state["frozen_protocol"])
        if source_lock() != execution_sources:
            raise ValueError("V5 confirmation execution source changed during capture")
        state.update(phase="audit_native_pixel_isolation", capture=record(series.report))
        A.write_json(STATUS, state)
        audit = phase_job("pixel-audit", "script/audit_unity_v5_confirmation_pixels.py", [])
        if audit["status"] != "passed":
            if PIXEL_GATE.exists():
                state["pixel_gate"] = record(PIXEL_GATE)
            raise RuntimeError(
                "Native pixel isolation did not pass; model evaluation remains sealed"
            )
        if A.read_json(PIXEL_GATE)["full_scoped_pixel_isolation_passed"] is not True:
            raise RuntimeError("Pixel isolation receipt did not certify the full cohort")
        if source_lock() != execution_sources:
            raise ValueError("V5 confirmation execution source changed during pixel audit")

        state.update(
            phase="formal_model_and_exact_psnr_evaluation",
            pixel_gate=record(PIXEL_GATE),
            formal_evaluation_started=True,
        )
        A.write_json(STATUS, state)
        evaluation = phase_job(
            "evaluation",
            "script/evaluate_unity_v5_confirmation.py",
            [
                "--pixel-gate-sha256",
                state["pixel_gate"]["sha256"],
            ],
        )
        if evaluation["status"] != "passed":
            raise RuntimeError("Formal model evaluation failed; preserve its sealed attempt")
        state.update(
            status="machine_evaluation_complete_awaiting_independent_human_ratings",
            phase="blind_human_confirmation",
            evaluation=record(EVALUATION),
        )
    except BaseException as error:
        state.update(status="stopped", error=repr(error))
        raise
    finally:
        state["wall_seconds"] = time.perf_counter() - started
        A.write_json(STATUS, state)


if __name__ == "__main__":
    main()
