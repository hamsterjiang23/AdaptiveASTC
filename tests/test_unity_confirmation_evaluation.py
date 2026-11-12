"""Preconditions and bounded paired execution before opening the real confirmation cohort."""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import numpy as np
import pytest
from numpy.typing import NDArray
from PIL import Image

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore as A
from adaptive_astc.utils.unity_evaluation_seal import UnityEvaluationSeal as Seal
from reproductions.unity_search_baseline.capture_policy import UnityCapturePolicyBinding
from reproductions.unity_search_baseline.confirmation_evaluation import (
    UnityConfirmationEvaluation as V,
)
from reproductions.unity_search_baseline.confirmation_evidence import UnityConfirmationEvidence as E
from reproductions.unity_search_baseline.native_data_pipeline import UnityNativeDataPipeline as P
from tests.test_unity_capture_input import captured_row
from tests.test_unity_capture_output import Quality
from tests.test_unity_deployment import FakePredictor, RecordingBackend
from tests.test_unity_evaluation_seal import identity
from tests.test_unity_search_policy import policy


def training() -> JsonDict:
    artifacts = {"best.pt": "a", "best-validation.npz": "b", "best-decisions.json": "c"}
    return {
        "config": {"smoke": False, "train_image_indices": []},
        "status": "completed",
        "test_opened": False,
        "training_updates": 100,
        "checkpoint_sha256": "a",
        "best_artifacts_sha256": artifacts,
        "checkpoint_audit": {
            "status": "passed",
            "test_opened": False,
            "metrics": {"count": 1000, "accuracy": 0.91},
            "checkpoint_sha256": "a",
            "predictions_sha256": "b",
            "selected_artifacts_sha256": dict(artifacts),
        },
    }


@pytest.mark.parametrize(
    "changed",
    [
        "none",
        "smoke",
        "subset",
        "unfinished",
        "test",
        "updates",
        "audit",
        "counts",
        "accuracy",
        "nan",
        "artifacts",
        "checkpoint",
        "predictions",
    ],
)
def test_completed_validation_selection_required(changed: str) -> None:
    report = training()
    if changed == "smoke":
        report["config"]["smoke"] = True
    if changed == "subset":
        report["config"]["train_image_indices"] = [0]
    if changed == "unfinished":
        report["status"] = "training"
    if changed == "test":
        report["test_opened"] = True
    if changed == "updates":
        report["training_updates"] = 0
    if changed == "audit":
        report["checkpoint_audit"]["status"] = "pending"
    if changed == "counts":
        report["checkpoint_audit"]["metrics"]["count"] = 2
    if changed == "accuracy":
        report["checkpoint_audit"]["metrics"]["accuracy"] = 0.89
    if changed == "nan":
        report["checkpoint_audit"]["metrics"]["accuracy"] = float("nan")
    if changed == "artifacts":
        report["best_artifacts_sha256"]["extra"] = "d"
    if changed == "checkpoint":
        report["checkpoint_sha256"] = "wrong"
    if changed == "predictions":
        report["checkpoint_audit"]["predictions_sha256"] = "wrong"
    if changed == "none":
        E.validate_training(report)
    else:
        with pytest.raises(ValueError):
            E.validate_training(report)


def model_evidence(
    root: Path,
    name: str,
    parent: JsonDict | None = None,
    image_pooling: str | None = "mean",
) -> JsonDict:
    run = root / name
    run.mkdir()
    config_path, report_path = root / f"{name}-config.json", root / f"{name}.json"
    corpus = root / "corpus"
    corpus.mkdir(exist_ok=True)
    A.write_json(
        corpus / "corpus.json",
        {
            "status": "passed",
            "test_opened": False,
            "counts": {"train": 10000, "validation": 1000},
            "splits": {"train": [{}] * 10000, "validation": [{}] * 1000},
        },
    )
    launched: JsonDict = {"output": str(run), "report": str(report_path), "smoke": False}
    report = training()
    settings = {
        **report["config"],
        **launched,
        "corpus": str(corpus),
        "corpus_sha256": A.sha256_file(corpus / "corpus.json"),
        "corpus_fingerprint": "same-development-inputs",
    }
    if image_pooling is not None:
        settings["image_pooling"] = image_pooling
    item: JsonDict = {"job": {"expected_script": "script/train_unity_quality.py"}}
    if parent is not None:
        initial = A.read_json(Path(parent["report"]["path"]))
        launched.update(
            training_report=parent["report"]["path"],
            training_report_sha256=parent["report"]["sha256"],
            patches_per_image=4,
        )
        settings.update(
            stage="Frozen encoder image-head refit",
            initial_training_report=launched["training_report"],
            initial_training_report_sha256=launched["training_report_sha256"],
            head_patch_views=4,
            patches_per_image=4,
        )
        report.update(
            encoder_and_channel_head_unchanged=True,
            initial_training_updates=initial["training_updates"],
            training_source_binding={
                "archive": None,
                "sources": [
                    {
                        "relative_path": Path(path).relative_to(root).as_posix(),
                        "training_sha256": digest,
                    }
                    for path, digest in initial["config"]["source_sha256"].items()
                ],
            },
        )
        item.update(
            initial_training=parent, job={"expected_script": "script/refit_unity_image_head.py"}
        )
    A.write_json(config_path, launched)
    settings["source_sha256"] = {str(config_path): A.sha256_file(config_path)}
    artifacts = {}
    for artifact in ("best.pt", "best-validation.npz", "best-decisions.json"):
        (run / artifact).write_bytes(artifact.encode())
        artifacts[artifact] = A.sha256_file(run / artifact)
    report.update(
        config=settings, best_artifacts_sha256=artifacts, checkpoint_sha256=artifacts["best.pt"]
    )
    report["checkpoint_audit"].update(
        selected_artifacts_sha256=artifacts,
        checkpoint_sha256=artifacts["best.pt"],
        predictions_sha256=artifacts["best-validation.npz"],
    )
    A.write_json(run / "config.json", settings)
    A.write_json(run / "checkpoint-audit.json", report["checkpoint_audit"])
    A.write_json(report_path, report)
    item.update(
        config={"path": str(config_path), "sha256": A.sha256_file(config_path)},
        report={"path": str(report_path), "sha256": A.sha256_file(report_path)},
    )
    return item


@pytest.mark.parametrize(
    "changed",
    [
        "none",
        "legacy_pooling",
        "low_final",
        "unfinished_parent",
        "source",
        "frozen",
        "archive",
        "lineage",
    ],
)
def test_head_stage_requires_full_initial_training_and_final_ninety_percent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, changed: str
) -> None:
    pooling = None if changed == "legacy_pooling" else "mean"
    parent = model_evidence(tmp_path, "initial", image_pooling=pooling)
    initial_path = Path(parent["report"]["path"])
    initial = A.read_json(initial_path)
    initial["checkpoint_audit"]["metrics"]["accuracy"] = 0.4
    if changed == "unfinished_parent":
        initial["status"] = "running"
    A.write_json(initial_path, initial)
    A.write_json(tmp_path / "initial/checkpoint-audit.json", initial["checkpoint_audit"])
    parent["report"]["sha256"] = A.sha256_file(initial_path)
    item = model_evidence(tmp_path, "head", parent, image_pooling=pooling)
    path = Path(item["report"]["path"])
    report = A.read_json(path)
    if changed == "low_final":
        report["checkpoint_audit"]["metrics"]["accuracy"] = 0.89
    if changed == "source":
        Path(parent["config"]["path"]).write_text("changed", encoding="utf-8")
    if changed == "frozen":
        report["encoder_and_channel_head_unchanged"] = False
    if changed == "archive":
        parent["training_source_archive"] = str(tmp_path / "unrelated-archive")
    if changed == "lineage":
        report["initial_training_updates"] += 1
    A.write_json(path, report)
    A.write_json(tmp_path / "head/checkpoint-audit.json", report["checkpoint_audit"])
    item["report"]["sha256"] = A.sha256_file(path)
    scripts = []

    def job(self: E, value: JsonDict, script: str, config_path: Path) -> None:
        assert script == value["expected_script"] and config_path.is_file()
        scripts.append(script)

    monkeypatch.setattr(E, "job", job)
    evidence = E(tmp_path)
    if changed in {"none", "legacy_pooling"}:
        assert evidence.model(item) == report
        assert scripts == ["script/refit_unity_image_head.py", "script/train_unity_quality.py"]
        evidence.verify()
        (tmp_path / "initial/best.pt").write_bytes(b"changed")
        with pytest.raises(ValueError, match="changed"):
            evidence.verify()
    else:
        with pytest.raises(ValueError):
            evidence.model(item)


def test_initial_stage_cannot_bypass_cycle_or_numeric_checks(tmp_path: Path) -> None:
    item = model_evidence(tmp_path, "initial")
    with pytest.raises(ValueError, match="Cyclic"):
        E(tmp_path)._model(item, require_accuracy=False, ancestors={Path(item["report"]["path"])})
    report = training()
    report["checkpoint_audit"]["metrics"]["accuracy"] = float("nan")
    with pytest.raises(ValueError):
        E.validate_training(report, require_accuracy=False)


@pytest.mark.parametrize("changed", ["split", "hash", "order"])
def test_only_confirmation_cross_split_pairs_block(changed: str) -> None:
    fields = {
        "reference": "reference.png",
        "reference_sha256": "reference-hash",
        "width": 64,
        "height": 64,
        "rgba_identity": "identity",
        "rgba_sha256": "pixels",
        "observed_options": {},
    }
    projected = [
        {**fields, "path": str(i), "source_split": s}
        for i, s in enumerate(["train", "validation", "confirmation", "confirmation"])
    ]
    rows = [
        {
            **row,
            "source_md4": "md4",
            "run_id": "capture",
            "callback_rgba_sha256": "pixels",
            "selected_block_size": "8x8",
            "selected_preset": "medium",
        }
        for row in projected
    ]
    exact = {"rows": rows, "rgba_groups": [{"row_indices": [0, 1]}, {"row_indices": [2, 3]}]}
    near = {
        "rows": copy.deepcopy(projected),
        "near_pairs": [{"left_row_indices": [0], "right_row_indices": [1]}],
    }
    assert not any(E.overlaps(exact, near).values())
    exact["rgba_groups"].append({"row_indices": [0, 2]})
    near["near_pairs"].append({"left_row_indices": [1], "right_row_indices": [2, 3]})
    assert E.overlaps(exact, near) == {
        "exact_confirmation_overlap_groups": 1,
        "near_confirmation_overlap_pairs": 1,
    }
    if changed == "split":
        near["rows"][0]["source_split"] = "confirmation"
    elif changed == "hash":
        near["rows"][0]["rgba_sha256"] = "other"
    else:
        near["rows"].reverse()
    with pytest.raises(ValueError, match="different rows"):
        E.overlaps(exact, near)


@pytest.mark.parametrize(
    "changed", ["none", "split", "images", "warmups", "repetitions", "chunks", "preset"]
)
def test_entire_confirmation_protocol_is_required(changed: str) -> None:
    config = {
        "split": "confirmation",
        "images": 2000,
        "warmups": 1,
        "repetitions": 3,
        "image_chunk_size": 8,
        "fixed8_preset": "medium",
    }
    alterations = {
        "split": ("split", "validation"),
        "images": ("images", 2),
        "warmups": ("warmups", True),
        "repetitions": ("repetitions", 1),
        "chunks": ("image_chunk_size", 2000),
        "preset": ("fixed8_preset", "unknown"),
    }
    if changed == "none":
        V.validate_config(config)
    else:
        key, value = alterations[changed]
        config[key] = value
        with pytest.raises(ValueError):
            V.validate_config(config)


@pytest.mark.parametrize(
    "case", ["passed", "utf8_absolute", "running", "other_command", "changed_job", "extra_flags"]
)
def test_completed_job_binding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str) -> None:
    job, config = tmp_path / "job.json", tmp_path / "config.json"
    A.write_json(
        job,
        {
            "command": [
                sys.executable,
                "-u",
                "wrong" if case == "other_command" else "script/train_unity_quality.py",
                "--config",
                str(config),
            ]
        },
    )
    if case == "utf8_absolute":
        A.write_json(
            job,
            {
                "command": [
                    sys.executable,
                    "-X",
                    "utf8",
                    "-u",
                    str(tmp_path / "script/train_unity_quality.py"),
                    "--config",
                    str(config),
                ]
            },
        )
    elif case == "extra_flags":
        A.write_json(
            job,
            {
                "command": [
                    sys.executable,
                    "-c",
                    "print('unrelated')",
                    "-u",
                    "script/train_unity_quality.py",
                    "--config",
                    str(config),
                ]
            },
        )
    receipt = job.with_name("receipt.json")
    A.write_json(receipt, {"status": "passed"})
    item = {"job_config": str(job), "sha256": A.sha256_file(job)}
    if case == "changed_job":
        A.write_json(job, {})

    def observe(value: JsonDict) -> JsonDict:
        assert value == item
        return {
            "status": "running" if case == "running" else "passed",
            "receipt_sha256": A.sha256_file(receipt),
        }

    monkeypatch.setattr(P, "dependency_status", staticmethod(observe))
    evidence = E(tmp_path)
    if case in {"passed", "utf8_absolute"}:
        evidence.job(item, "script/train_unity_quality.py", config)
        evidence.verify()
        A.write_json(receipt, {"status": "changed"})
        with pytest.raises(ValueError, match="changed"):
            evidence.verify()
    else:
        with pytest.raises(ValueError):
            evidence.job(item, "script/train_unity_quality.py", config)


def test_failed_attempt_can_retry_only_same_protocol_at_new_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = identity(tmp_path)
    source = next(iter(base["files_sha256"]))
    monkeypatch.setattr(
        V, "execution_sources", staticmethod(lambda root: {source: A.sha256_file(Path(source))})
    )
    seals = []
    config: JsonDict = {
        "split": "confirmation",
        "images": 2000,
        "warmups": 1,
        "repetitions": 3,
        "image_chunk_size": 8,
        "fixed8_preset": "medium",
        "sources_sha256": base["files_sha256"],
    }
    for attempt in range(3):
        output = tmp_path / f"experiment report/.local/attempt-{attempt}"
        report = tmp_path / f"experiment report/attempt-{attempt}.json"
        config.update(output=str(output), report=str(report))
        if attempt == 2:
            config["fixed8_preset"] = "fastest"
        path = tmp_path / f"config-{attempt}.json"
        A.write_json(path, config)
        runner = V(tmp_path, path)
        value = copy.deepcopy(base)
        value["decision"]["evaluation_config_sha256"] = runner.protocol_sha256
        value["files_sha256"] = runner.seal_files()
        seal = Seal(tmp_path / "registry", value)
        if attempt == 2:
            with pytest.raises(ValueError, match="already sealed"):
                seal.acquire()
            continue
        seals.append(seal.acquire())
        output.mkdir(parents=True)
        A.write_json(report, {"status": "failed" if attempt == 0 else "passed"})
        with pytest.raises(ValueError, match="fresh local"):
            V(tmp_path, path)

        def execute() -> None:
            runner.evidence.verify()
            if attempt == 0:
                raise RuntimeError("fixture interruption")

        if attempt == 0:
            with pytest.raises(RuntimeError, match="fixture interruption"):
                seal.forward(execute)
        else:
            seal.forward(execute)
            A.write_json(path, {})
            with pytest.raises(ValueError, match="changed"):
                runner.evidence.verify()
    assert seals[0] == seals[1]
    attempts = [A.read_json(p) for p in (seal.path.parent / "attempts").glob("*.json")]
    assert sorted(item["status"] for item in attempts) == ["failed", "passed"]
    assert A.read_json(tmp_path / "experiment report/attempt-0.json")["status"] == "failed"


class Backend(RecordingBackend):
    def decode_payload(
        self, payload: bytes, width: int, height: int, block: int, *, srgb: bool
    ) -> tuple[NDArray[np.uint8], float]:
        assert self.calls[-1]["rgba"].shape == (height, width, 4)
        return self.calls[-1]["rgba"].copy(), 0.001


@pytest.mark.parametrize("tamper", ["first_receipt", "first_output", "repetitions", "membership"])
def test_chunked_trial_counts_orders_and_measured_quality(tmp_path: Path, tamper: str) -> None:
    rows = []
    for i in range(3):
        directory = tmp_path / str(i)
        directory.mkdir()
        row = captured_row(directory)
        asset = f"Assets/image{i}.png"
        row["path"] = row["actual_options"]["path"] = row["import_metadata"]["asset"] = asset
        row["selection"]["asset"] = asset
        rows.append(row)
    runner = object.__new__(V)
    runner.root, runner.output, runner.report = tmp_path, tmp_path / "out", tmp_path / "report.json"
    runner.config = {"image_chunk_size": 2, "fixed8_preset": "medium"}
    runner.evidence = E(tmp_path)
    binding = cast(UnityCapturePolicyBinding, SimpleNamespace(policy=policy(), verify=lambda: None))
    runner.evidence.policies = [binding]
    predictor, backend = FakePredictor(), Backend()
    predictor.target_index = 0
    state: JsonDict = {"test_opened": False}
    result = runner.evaluate(rows, [0, 0, 0], predictor, [backend], Quality(), state)
    assert predictor.calls == 8 and len(backend.calls) == 24
    assert result["summary"]["prediction"]["measured_encoding_calls"] == 9
    assert result["summary"]["prediction"]["warmup_encoding_calls"] == 3
    assert result["summary"]["prediction"]["footprint_accuracy"] == 1
    assert result["summary"]["prediction"]["strict_quality_pass_rate"] == 0
    assert state["test_opened"] and state["chunks_completed"] == 8
    assert state["completed_images_this_repetition"] == 3
    for repeat in range(4):
        for chunk_index, start in enumerate([0, 2]):
            record = A.read_json(runner.output / f"repeat-{repeat}/{start:05d}-receipt.json")
            assert record["warmup"] == (repeat == 0)
            assert record["order"][0] == (
                "prediction" if (repeat + chunk_index) % 2 == 0 else "fixed8"
            )
            for arm in ["prediction", "fixed8"]:
                folder = runner.output / f"repeat-{repeat}/{start:05d}-{arm}"
                for name, digest in record["arms"][arm]["outputs_sha256"].items():
                    assert A.sha256_file(folder / name) == digest
                with Image.open(folder / "00000.png") as image:
                    assert np.asarray(image).shape == (7, 250, 4)
    manifest = result["outputs_manifest"]
    assert A.sha256_file(Path(manifest["path"])) == manifest["sha256"]
    listing = A.read_json(Path(manifest["path"]))
    assert len(listing["chunks"]) == 8
    runner.verify_outputs(listing, len(rows))
    if tamper == "first_receipt":
        A.write_json(Path(listing["chunks"][0]["path"]), {})
    elif tamper == "first_output":
        (runner.output / "repeat-0/00000-prediction/00000.astc").write_bytes(b"changed")
    elif tamper == "repetitions":
        A.write_json(Path(listing["repetitions"]["path"]), {})
    else:
        listing["chunks"].pop()
    with pytest.raises(ValueError):
        runner.verify_outputs(listing, len(rows))
