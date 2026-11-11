from __future__ import annotations

from pathlib import Path

import pytest

import reproductions.unity_search_baseline.training_queue as queue_module
from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.common.jobs import ReproductionJob
from reproductions.unity_search_baseline.native_data_pipeline import UnityNativeDataPipeline as P
from reproductions.unity_search_baseline.training_queue import UnityTrainingQueue


def data_fixture(tmp_path: Path) -> tuple[UnityTrainingQueue, Path, Path]:
    queue = object.__new__(UnityTrainingQueue)
    queue.output = tmp_path / "experiment report/.local/training"
    queue.reports = tmp_path / "reports"
    pipeline = tmp_path / "pipeline-config.json"
    public = tmp_path / "pipeline-report.json"
    corpus = tmp_path / "pipeline/corpus"
    counts = {"train": 10000, "validation": 1000}
    A.write_json(pipeline, {"report": str(public), "output": str(corpus.parent)})
    A.write_json(
        corpus / "corpus.json",
        {
            "status": "passed",
            "test_opened": False,
            "coverage": "complete",
            "counts": counts,
            "expected_full_counts": counts,
            "splits": {k: [{}] * n for k, n in counts.items()},
        },
    )
    stages = []
    for name in ["prepare", "assembly", "dataset", "interface"]:
        path = tmp_path / f"{name}.json"
        A.write_json(
            path,
            {
                "status": "passed",
                "test_opened": False,
                "training_updates": 0,
                "counts": counts,
                "unique_images": counts,
                "coverage": "complete",
                "results": {
                    k: {"exact_targets": {"count": n, "accuracy": 1.0, "full_choice_accuracy": 1.0}}
                    for k, n in counts.items()
                },
            },
        )
        stages.append({"name": name, "report": str(path), "report_sha256": A.sha256_file(path)})
    A.write_json(
        public,
        {
            "status": "passed",
            "mode": "complete",
            "config_sha256": A.sha256_file(pipeline),
            "expected_counts": counts,
            "test_opened": False,
            "training_updates": 0,
            "stages": stages,
            "corpus": str(corpus),
            "corpus_sha256": A.sha256_file(corpus / "corpus.json"),
        },
    )
    queue.config = {
        "pipeline_config": str(pipeline),
        "pipeline_config_sha256": A.sha256_file(pipeline),
        "recipe": {},
    }
    return queue, public, corpus


def test_complete_four_stage_corpus_can_bind_formal_training(tmp_path: Path) -> None:
    queue, _, corpus = data_fixture(tmp_path)
    assert queue.complete_corpus() == (corpus, A.sha256_file(corpus / "corpus.json"))


@pytest.mark.parametrize(
    "case",
    [
        "partial",
        "missing_stage",
        "test",
        "wrong_config",
        "row_count",
        "extra_split",
        "changed_corpus",
    ],
)
def test_incomplete_or_replaced_data_cannot_start_formal(tmp_path: Path, case: str) -> None:
    queue, report, corpus = data_fixture(tmp_path)
    result = A.read_json(report)
    document = A.read_json(corpus / "corpus.json")
    if case == "partial":
        document["coverage"] = "partial"
    elif case == "missing_stage":
        result["stages"].pop()
    elif case == "test":
        document["test_opened"] = True
    elif case == "wrong_config":
        result["config_sha256"] = "different"
    elif case == "row_count":
        document["splits"]["train"].pop()
    elif case == "extra_split":
        document["splits"]["test"] = [{}]
    else:
        document["unknown_change"] = True
    A.write_json(corpus / "corpus.json", document)
    if case != "changed_corpus":
        result["corpus_sha256"] = A.sha256_file(corpus / "corpus.json")
    A.write_json(report, result)
    with pytest.raises(ValueError):
        queue.complete_corpus()


@pytest.mark.parametrize("case", ["changed_report", "failed", "count", "coverage", "interface"])
def test_all_stage_evidence_is_required(tmp_path: Path, case: str) -> None:
    queue, report, _ = data_fixture(tmp_path)
    result = A.read_json(report)
    stage = result["stages"][-1 if case == "interface" else 0]
    path = Path(stage["report"])
    evidence = A.read_json(path)
    if case in {"changed_report", "failed"}:
        evidence["status"] = "failed"
    elif case == "count":
        evidence["counts"]["train"] = 9999
    elif case == "coverage":
        evidence["coverage"] = "partial"
    else:
        evidence["results"]["validation"]["exact_targets"]["full_choice_accuracy"] = 0.999
    A.write_json(path, evidence)
    if case != "changed_report":
        stage["report_sha256"] = A.sha256_file(path)
    A.write_json(report, result)
    with pytest.raises(ValueError):
        queue.complete_corpus()


def test_wait_observes_dependencies_before_gpu_resources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    queue = object.__new__(UnityTrainingQueue)
    queue.report = tmp_path / "state.json"
    events: list[str] = []

    def verify(self: UnityTrainingQueue) -> None:
        events.append("verify")

    def dependency(item: JsonDict) -> JsonDict:
        events.append("dependency")
        return {"status": "passed" if "sleep" in events else "running"}

    def resources() -> JsonDict:
        events.append("resources")
        return {"ready": True}

    def sleep(seconds: int) -> None:
        assert seconds == 30
        events.append("sleep")

    monkeypatch.setattr(UnityTrainingQueue, "verify_bindings", verify)
    monkeypatch.setattr(UnityTrainingQueue, "resources", staticmethod(resources))
    monkeypatch.setattr(P, "dependency_status", dependency)
    monkeypatch.setattr(queue_module.time, "sleep", sleep)
    state: JsonDict = {}
    queue.wait([{}], state, "cuda", gpu=True)
    assert events == ["verify", "dependency", "sleep", "verify", "dependency", "resources"]
    assert state["wait_seconds"]["cuda"] >= 0


def init_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    local = tmp_path / "experiment report/.local/queue"
    public = tmp_path / "experiment report/queue"
    smoke = tmp_path / "smoke.json"
    pipeline, job = tmp_path / "pipeline.json", tmp_path / "job.json"
    A.write_json(pipeline, {})
    A.write_json(
        job,
        {"command": ["python", "script/finish_unity_native_data.py", "--config", str(pipeline)]},
    )
    A.write_json(
        smoke,
        {
            "corpus": str(tmp_path / "corpus"),
            "corpus_sha256": "fixture",
            "output": str(local / "smoke"),
            "report": str(public / "smoke.json"),
            "smoke": True,
            "train_image_indices": list(range(32)),
            "epochs": 2,
        },
    )
    config = tmp_path / "queue.json"
    A.write_json(
        config,
        {
            "output": str(local),
            "reports": str(public),
            "report": str(tmp_path / "experiment report/queue.json"),
            "cuda_dependencies": [{}],
            "recipe": {},
            "smoke_config": str(smoke),
            "pipeline_config": str(pipeline),
            "data_dependency": {"job_config": str(job), "sha256": A.sha256_file(job)},
        },
    )

    def verify(self: UnityTrainingQueue) -> None:
        pass

    monkeypatch.setattr(UnityTrainingQueue, "verify_bindings", verify)
    return config, smoke


def test_matching_smoke_and_formal_recipe_is_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, _ = init_fixture(tmp_path, monkeypatch)
    queue = UnityTrainingQueue(tmp_path, path)
    assert not queue.output.exists()


@pytest.mark.parametrize(
    "case",
    ["queue", "formal", "formal_child", "job", "formal_report", "formal_config", "nested_reports"],
)
def test_stage_paths_cannot_alias_later_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    path, smoke_path = init_fixture(tmp_path, monkeypatch)
    config, smoke = A.read_json(path), A.read_json(smoke_path)
    output, reports = Path(config["output"]), Path(config["reports"])
    if case == "queue":
        smoke["output"] = str(output)
    elif case == "formal":
        smoke["output"] = str(output / "formal")
    elif case == "formal_child":
        smoke["output"] = str(output / "formal/nested")
    elif case == "job":
        smoke["output"] = str(output / "smoke-job")
    elif case == "formal_report":
        smoke["report"] = str(reports / "formal.json")
    elif case == "formal_config":
        smoke["report"] = str(reports / "formal-config.json")
    else:
        config["reports"] = str(output / "reports")
    A.write_json(smoke_path, smoke)
    A.write_json(path, config)
    with pytest.raises(ValueError):
        UnityTrainingQueue(tmp_path, path)
    assert not output.exists()


@pytest.mark.parametrize(
    "case",
    [
        "subset",
        "not_smoke",
        "one_batch",
        "learning_rate",
        "workers",
        "empty_dependencies",
        "wrong_data_job",
    ],
)
def test_bad_smoke_or_scope_rejected_before_training(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    path, smoke_path = init_fixture(tmp_path, monkeypatch)
    config, smoke = A.read_json(path), A.read_json(smoke_path)
    if case == "subset":
        config["recipe"]["train_image_indices"] = [0]
    elif case == "not_smoke":
        smoke.update(smoke=False, train_image_indices=[])
    elif case == "one_batch":
        smoke["train_image_indices"] = list(range(16))
    elif case in {"learning_rate", "workers"}:
        smoke[case] = 0.001 if case == "learning_rate" else 0
    elif case == "empty_dependencies":
        config["cuda_dependencies"] = []
    else:
        config["pipeline_config"] = str(tmp_path / "different.json")
    A.write_json(smoke_path, smoke)
    A.write_json(path, config)
    with pytest.raises(ValueError):
        UnityTrainingQueue(tmp_path, path)
    assert not Path(config["output"]).exists()


def test_failed_child_training_cannot_advance_to_formal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    queue, _, _ = data_fixture(tmp_path)
    queue.root, queue.report = tmp_path, tmp_path / "state.json"
    config = tmp_path / "training.json"
    A.write_json(config, {"report": str(tmp_path / "child.json")})

    def verify(self: UnityTrainingQueue) -> None:
        pass

    def failed(self: ReproductionJob) -> JsonDict:
        return {"status": "failed", "process_exit_code": 1}

    monkeypatch.setattr(UnityTrainingQueue, "verify_bindings", verify)
    monkeypatch.setattr(ReproductionJob, "run", failed)
    state: JsonDict = {"stages": []}
    with pytest.raises(RuntimeError, match="process failed"):
        queue.train("smoke", config, state)
    assert not state["stages"] and Path(state["current_job"]).exists()


@pytest.mark.parametrize("failure", [None, "smoke", "formal"])
def test_two_stage_order_and_no_test_goal_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str | None
) -> None:
    path, _ = init_fixture(tmp_path, monkeypatch)
    queue = UnityTrainingQueue(tmp_path, path)
    events: list[str] = []

    def wait(
        self: UnityTrainingQueue,
        dependencies: list[JsonDict],
        state: JsonDict,
        stage: str,
        *,
        gpu: bool,
    ) -> None:
        assert gpu
        events.append(f"wait_{stage}")

    def corpus(self: UnityTrainingQueue) -> tuple[Path, str]:
        events.append("bind_complete_corpus")
        return tmp_path / "full-corpus", "full-digest"

    def train(self: UnityTrainingQueue, name: str, config: Path, state: JsonDict) -> JsonDict:
        events.append(f"train_{name}")
        values = A.read_json(config)
        if name == "formal":
            assert values["corpus_sha256"] == "full-digest"
            assert not values["smoke"] and values["train_image_indices"] == []
        if name == failure:
            raise RuntimeError("child failed")
        state["stages"].append({"name": name})
        return {}

    monkeypatch.setattr(UnityTrainingQueue, "wait", wait)
    monkeypatch.setattr(UnityTrainingQueue, "complete_corpus", corpus)
    monkeypatch.setattr(UnityTrainingQueue, "train", train)
    if failure:
        with pytest.raises(RuntimeError, match="child failed"):
            queue.run()
    else:
        queue.run()
    state = A.read_json(queue.report)
    assert state["status"] == ("failed" if failure else "passed")
    assert not state["test_opened"] and not state["goal_complete"]
    if failure == "smoke":
        assert events == ["wait_cuda", "train_smoke"]
    else:
        assert events[:5] == [
            "wait_cuda",
            "train_smoke",
            "wait_data",
            "bind_complete_corpus",
            "train_formal",
        ]
        assert len(events) == (5 if failure else 6)


@pytest.mark.parametrize(
    "case", ["valid", "zero_updates", "missing_predictions", "changed_checkpoint", "test_opened"]
)
def test_child_receipt_requires_bound_reload_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    queue, _, _ = data_fixture(tmp_path)
    queue.root, queue.report = tmp_path, tmp_path / "state.json"
    output, report = queue.output / "smoke", queue.reports / "smoke.json"
    output.mkdir(parents=True)
    config_path = tmp_path / "training.json"
    config = {"output": str(output), "report": str(report), "smoke": True}
    A.write_json(config_path, config)
    selected = {}
    for name in ["best.pt", "best-validation.npz", "best-decisions.json"]:
        (output / name).write_bytes(b"fixture")
        selected[name] = A.sha256_file(output / name)
    result = {
        "status": "passed_smoke",
        "test_opened": False,
        "training_updates": 4,
        "config": config,
        "checkpoint_sha256": selected["best.pt"],
        "best_artifacts_sha256": dict(selected),
        "checkpoint_audit": {
            "status": "passed",
            "test_opened": False,
            "metrics": {},
            "selected_artifacts_sha256": dict(selected),
            "checkpoint_sha256": selected["best.pt"],
        },
    }
    if case == "zero_updates":
        result["training_updates"] = 0
    elif case == "missing_predictions":
        result["best_artifacts_sha256"].pop("best-validation.npz")
    elif case == "changed_checkpoint":
        (output / "best.pt").write_bytes(b"changed")
    elif case == "test_opened":
        result["checkpoint_audit"]["test_opened"] = True
    A.write_json(report, result)

    def verify(self: UnityTrainingQueue) -> None:
        pass

    def passed(self: ReproductionJob) -> JsonDict:
        receipt = {"status": "passed", "process_exit_code": 0, "wall_seconds": 0.1}
        A.write_json(self.config.parent / "receipt.json", receipt)
        return receipt

    monkeypatch.setattr(UnityTrainingQueue, "verify_bindings", verify)
    monkeypatch.setattr(ReproductionJob, "run", passed)
    state: JsonDict = {"stages": []}
    if case == "valid":
        queue.train("smoke", config_path, state)
        assert len(state["stages"]) == 1
    else:
        with pytest.raises(ValueError):
            queue.train("smoke", config_path, state)
        assert not state["stages"]
