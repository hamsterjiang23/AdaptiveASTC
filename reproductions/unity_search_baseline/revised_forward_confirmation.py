"""Prepare the frozen forward system with approved revised-cohort evidence."""

from __future__ import annotations

import time
from pathlib import Path

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_capture_input import UnityCaptureInputAdapter
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline.confirmation_revision_pixels import (
    UnityConfirmationRevisionPixelAudit,
)
from reproductions.unity_search_baseline.forward_confirmation import (
    UnityForwardConfirmationEvaluation,
)
from reproductions.unity_search_baseline.revised_confirmation_evidence import (
    UnityRevisedConfirmationEvidence,
)


class UnityRevisedForwardConfirmationEvaluation(UnityForwardConfirmationEvaluation):
    @staticmethod
    def execution_sources(root: Path) -> dict[str, str]:
        names = [
            "reproductions/unity_search_baseline/revised_confirmation_evidence.py",
            "reproductions/unity_search_baseline/revised_forward_confirmation.py",
            "script/evaluate_unity_revised_forward_confirmation.py",
        ]
        return (
            UnityForwardConfirmationEvaluation.execution_sources(root)
            | UnityConfirmationRevisionPixelAudit.execution_sources(root)
            | {name: A.sha256_file(root / name) for name in names}
        )

    @staticmethod
    def validate_config(config: JsonDict) -> None:
        UnityForwardConfirmationEvaluation.validate_config(config)
        if config["cohort_evidence_kind"] != "approved_revised_confirmation_v3" or (
            not isinstance(config["pixel_audit"], dict)
            or set(config["pixel_audit"]) != {"revised_cohort", "registry_pipeline"}
        ):
            raise ValueError("Require explicit revised-cohort evidence and shared registry context")

    def __init__(self, root: Path, path: Path) -> None:
        super().__init__(root, path)
        evidence = UnityRevisedConfirmationEvidence(self.root, self.config["system"])
        evidence.files = dict(self.evidence.files)
        self.evidence = evidence

    def prepare(self) -> JsonDict:
        started = time.perf_counter()
        state = super().prepare()
        try:
            pipeline, pixels = self.evidence.pixel_audit(self.config["pixel_audit"])
            rows, indices = self.evidence.captures(pipeline, pixels)
            adapter = UnityCaptureInputAdapter(rows, "confirmation")
            if adapter.fingerprint != self.evidence.input_fingerprint:
                raise ValueError("Revised confirmation input projection fingerprint changed")
            self.evidence.verify()
            assert pipeline.confirmation is not None
            state.update(
                status="passed_revised_cohort_protocol_preparation",
                cohort_evidence_ready=True,
                confirmation_images=len(rows),
                native_policy_indices=len(indices),
                native_policy_contexts=len(self.evidence.policies),
                native_input_fingerprint=adapter.fingerprint,
                registry_parent_manifest_sha256=(
                    pipeline.confirmation.smoke.reservation["manifest_sha256"]
                ),
                pending=["Future explicit confirmation execution authorization"],
                inputs_sha256=self.evidence.files,
            )
        except BaseException as error:
            state.update(status="failed", error=repr(error))
            raise
        finally:
            state["wall_seconds"] = time.perf_counter() - started
            A.write_json(Path(self.config["preparation_report"]), state)
        return state
