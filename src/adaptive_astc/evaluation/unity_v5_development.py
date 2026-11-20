"""Publish paired full V5 results, machine gates and a model-bound human review packet."""

from __future__ import annotations

from pathlib import Path

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_tile_archive import UnityTileArchive
from adaptive_astc.evaluation.unity_dense_review import UnityDenseReview
from adaptive_astc.evaluation.unity_dense_review_scoring import UnityDenseReviewScoring
from adaptive_astc.evaluation.unity_dense_screening import UnityDenseScreening
from adaptive_astc.evaluation.unity_tile_oracle import UnityTileOracle
from adaptive_astc.utils.artifacts import ArtifactStore as A


class UnityV5Development:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        history = root / "experiment report/unity-accuracy90-20261111"
        self.raw = root / "experiment report/.local/unity-v5-20261119"
        self.progress = A.read_json(root / "experiment report/unity-v5-20261119/progress.json")
        self.archive = UnityTileArchive(history / "unity-v2-data-inputs.json")
        self.screening = UnityDenseScreening(
            self.archive, history / "unity-development-corpus11000-v2-interface.json"
        )
        self.review = UnityDenseReview(self.archive)

    def read_record(self, record: JsonDict) -> JsonDict:
        return self.archive.read_bound_json(self.root / record["path"], record["sha256"], dict)

    @staticmethod
    def file(path: Path) -> JsonDict:
        return {"path": str(path.resolve()), "sha256": A.sha256_file(path)}

    def read_model(self, run: Path, mode: str, corpus_sha: str) -> tuple[JsonDict, JsonDict]:
        report = A.read_json(run / "report.json")
        if (
            report["status"] != "passed"
            or report["test_opened"] is not False
            or report["stage"] != "full"
            or not report["checkpoint_reloaded"]
            or report["training_updates"] <= 0
            or report["corpus_sha256"] != corpus_sha
            or report["counts"] != {"train": 10000, "validation": 1000}
        ):
            raise ValueError(f"{mode} model did not complete the full V5 development protocol")
        if mode == "frozen" and not report["frozen_native_parameters_and_buffers_unchanged"]:
            raise ValueError("Frozen model changed the V3 native state")
        if mode == "joint" and (report["mode"] != "joint" or not report["backbone_updated"]):
            raise ValueError("Joint result lacks verified native encoder updates")
        if A.sha256_file(run / "best-head.pt") != report["best_checkpoint_sha256"]:
            raise ValueError("Full V5 checkpoint digest changed")
        result = self.archive.read_bound_json(
            run / "best-validation.json", report["best_validation_sha256"], dict
        )
        if [row["index"] for row in result["images"]] != list(range(1000)):
            raise ValueError("Full V5 checkpoint does not cover the ordered 1000 validation images")
        return report, result

    @staticmethod
    def verify_shared_targets(first: JsonDict, second: JsonDict) -> None:
        for a, b in zip(first["images"], second["images"], strict=True):
            if a["regions"] != b["regions"]:
                raise ValueError("V5 model reports use different true tile regions")
            for view, thresholds in a["bad"].items():
                for y, regions in thresholds.items():
                    for region, counts in regions.items():
                        if counts["true"] != b["bad"][view][y][region]["true"]:
                            raise ValueError("Frozen and joint reports use different exact labels")

    def run(
        self,
        label_corpus: Path,
        frozen_run: Path,
        joint_run: Path,
        joint_native: Path,
        output: Path,
    ) -> JsonDict:
        if not output.resolve().is_relative_to(self.raw):
            raise ValueError("V5 raw evaluation must stay in the private experiment directory")
        label_sha = A.sha256_file(label_corpus)
        labels = self.archive.read_bound_json(label_corpus, label_sha, dict)
        oracle = UnityTileOracle(self.archive, label_corpus, labels)
        frozen, baseline = self.read_model(frozen_run, "frozen", label_sha)
        joint, changed = self.read_model(joint_run, "joint", label_sha)
        if joint["parent_sha256"] != frozen["parent_sha256"] or joint[
            "frozen_report_sha256"
        ] != A.sha256_file(frozen_run / "report.json"):
            raise ValueError("Joint model was not initialized from this frozen V5 model")
        self.verify_shared_targets(baseline, changed)
        step = self.read_record(self.progress["step_baseline"])
        if (
            step["status"] != "passed"
            or step["color_coverage"] != "complete"
            or step["development_corpus_sha256"] != self.archive.sha256
            or step["test_opened"]
            or step["candidate"] != [8, "fastest"]
        ):
            raise ValueError("Step control differs from the V5 development cohort")
        readiness = self.read_record(self.progress["joint_review_readiness"])
        partition = self.read_record(readiness["review_partition"])
        if partition != self.review.partition():
            raise ValueError("Frozen human review partition changed")
        label_audit = self.read_record(self.progress["label_audit"])
        if label_audit["status"] != "passed" or label_audit["images"] != 32:
            raise ValueError("V5 label audit prerequisite is absent")
        parent = self.read_record(readiness["native_parent_replay"])
        replay = A.read_json(joint_native)
        epoch = joint["history"][joint["best_epoch"] - 1]
        epoch_replay = A.read_json(
            joint_run / f"epoch-{joint['best_epoch']:03d}-native-replay.json"
        )
        if (
            replay["status"] != "passed"
            or replay["checkpoint_sha256"] != joint["best_native_checkpoint_sha256"]
            or A.sha256_file(joint_run / "best-native.pt") != replay["checkpoint_sha256"]
            or replay["validation_indices"] != list(range(1000))
            or replay["test_opened"]
            or replay["control_metrics"] != parent["control_metrics"]
            or replay["control_trace_sha256"] != parent["control_trace_sha256"]
            or replay["metrics"] != epoch["native_metrics"]
            or replay["no_aggregate_regression"] != joint["no_aggregate_regression"]
            or replay["choices"] != epoch_replay["choices"]
            or replay["new_strict_regressions"] != epoch["new_strict_regressions"]
        ):
            raise ValueError(
                "Independent best-native replay disagrees with the audited joint checkpoint"
            )

        output.mkdir(parents=True, exist_ok=False)
        outcomes = {}
        model_runs = {"frozen": (baseline, frozen_run), "joint": (changed, joint_run)}
        for mode, (prediction, run) in model_runs.items():
            screening = self.screening.compare(prediction["images"], step["rows"])
            calibrated_step = UnityDenseReviewScoring.step_baseline(
                prediction["images"], step["rows"], partition, self.screening.candidate
            )
            path = output / f"{mode}-evaluation.json"
            A.write_json(
                path,
                {
                    "tile_metrics": prediction["summary"],
                    "screening": screening,
                    "calibrated_step": calibrated_step,
                },
            )
            outcomes[mode] = {
                "model_report": self.file(run / "report.json"),
                "checkpoint": self.file(run / "best-head.pt"),
                "validation": self.file(run / "best-validation.json"),
                "evaluation": self.file(path),
                "beats_step": calibrated_step["dense_beats_step_on_primary_gate"],
            }
        choose_joint = (
            joint["improved_dense_vs_frozen"]
            and replay["no_aggregate_regression"]
            and outcomes["joint"]["beats_step"] is True
        )
        chosen = "joint" if choose_joint else "frozen"
        if chosen == "frozen" and outcomes["frozen"]["beats_step"] is not True:
            admission = "no_dense_variant_passed_machine_gate"
        else:
            admission = "machine_gate_passed_pending_human_evaluation"
        oracle_path = output / "historical-oracle-audit.json"
        label_oracle = oracle.compare_known_pool(step["rows"])
        archived_oracle = self.read_record(self.progress["historical_gradient_pool"])
        if (
            archived_oracle["status"] != "passed"
            or archived_oracle["smoke"]
            or archived_oracle["test_opened"]
            or archived_oracle["step_report_sha256"] != self.progress["step_baseline"]["sha256"]
            or archived_oracle["development_corpus_sha256"] != self.archive.sha256
            or any(archived_oracle[key] != value for key, value in label_oracle.items())
        ):
            raise ValueError("Full V5 label oracle does not reproduce the independent pixel audit")
        A.write_json(
            oracle_path,
            {
                **label_oracle,
                "matches_independent_archived_decodes": True,
                "archived_oracle_sha256": self.progress["historical_gradient_pool"]["sha256"],
            },
        )
        chosen_prediction, chosen_run = model_runs[chosen]
        packet = output / "review-packet"
        packet_strata = self.review.packet(
            packet, self.screening, partition, chosen_prediction["images"], step["rows"]
        )
        A.write_json(
            packet / "manifest.json",
            {
                "status": "awaiting_human_ratings",
                "training_stage": "full",
                "partition_sha256": readiness["review_partition"]["sha256"],
                "training_report_sha256": A.sha256_file(chosen_run / "report.json"),
                "validation_sha256": A.sha256_file(chosen_run / "best-validation.json"),
                "step_report_sha256": self.progress["step_baseline"]["sha256"],
                "strata": packet_strata,
                "confirmation_opened": False,
            },
        )
        result = {
            "status": "awaiting_human_ratings",
            "numeric_gate_status": admission,
            "selected_for_review": chosen,
            "formal_confirmation_execution_authorized": False,
            "confirmation_opened": False,
            "models": outcomes,
            "label_corpus": self.file(label_corpus),
            "parent_native_replay": readiness["native_parent_replay"],
            "joint_native_replay": self.file(joint_native),
            "joint_native_metrics": replay["metrics"],
            "joint_no_aggregate_regression": replay["no_aggregate_regression"],
            "joint_new_strict_regressions": replay["new_strict_regressions"],
            "joint_improved_dense_vs_frozen": joint["improved_dense_vs_frozen"],
            "oracle_audit": self.file(oracle_path),
            "review_manifest": self.file(packet / "manifest.json"),
            "rating_counts": {name: len(group["rows"]) for name, group in packet_strata.items()},
        }
        A.write_json(output / "report.json", result)
        return result
