"""Native cohort seals are immutable, race-safe and retain failed forward attempts."""

from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore as A
from adaptive_astc.utils.unity_evaluation_seal import UnityEvaluationSeal as Seal


def identity(root: Path) -> JsonDict:
    source = root / "bound-input.bin"
    source.write_bytes(b"unchanged-source")
    return {
        "schema": "unity_native_inference_v1",
        "split": "confirmation",
        "cohort_fingerprint": A.fingerprint("fixed-cohort"),
        "inputs_fingerprint": A.fingerprint("native-inputs"),
        "policies_fingerprint": A.fingerprint("original-policy"),
        "model": {"checkpoint_sha256": A.fingerprint("model")},
        "decision": {"zero_threshold": 0.5, "patch_size": 240},
        "runtime": {"torch": "fixture"},
        "files_sha256": {str(source): A.sha256_file(source)},
    }


def test_seal_exists_before_forward_and_same_contract_can_be_repeated(tmp_path: Path) -> None:
    value = identity(tmp_path)
    seal = Seal(tmp_path / "registry", value)
    first = seal.acquire()

    def operation() -> int:
        assert A.read_json(seal.path)["fingerprint"] == seal.fingerprint
        attempts = list((seal.path.parent / "attempts").glob("*.json"))
        assert len(attempts) == 1
        assert A.read_json(attempts[0])["status"] == "started"
        return 42

    assert seal.forward(operation) == 42
    assert Seal(tmp_path / "registry", value).acquire() == first
    assert A.read_json(next((seal.path.parent / "attempts").glob("*.json")))["status"] == "passed"


@pytest.mark.parametrize(
    "key",
    ["model", "decision", "runtime", "inputs_fingerprint", "policies_fingerprint", "files_sha256"],
)
def test_changed_contract_cannot_reopen_same_cohort(tmp_path: Path, key: str) -> None:
    value = identity(tmp_path)
    original = Seal(tmp_path / "registry", value)
    original.acquire()
    changed = copy.deepcopy(value)
    if key.endswith("fingerprint"):
        changed[key] = A.fingerprint("different")
    elif key == "files_sha256":
        extra = tmp_path / "other.bin"
        extra.write_bytes(b"other")
        changed[key][str(extra)] = A.sha256_file(extra)
    else:
        changed[key] = {"different": True}
    with pytest.raises(ValueError, match="already sealed"):
        Seal(tmp_path / "registry", changed).acquire()
    assert A.read_json(original.path)["identity"] == value


def test_forward_failure_is_recorded_and_does_not_clear_seal(tmp_path: Path) -> None:
    value = identity(tmp_path)
    seal = Seal(tmp_path / "registry", value)
    seal.acquire()

    def failed() -> None:
        raise RuntimeError("fixture CUDA failure")

    with pytest.raises(RuntimeError, match="fixture CUDA failure"):
        seal.forward(failed)
    attempt = A.read_json(next((seal.path.parent / "attempts").glob("*.json")))
    assert attempt["status"] == "failed" and attempt["test_opened"] is True
    seal.verify()
    changed = copy.deepcopy(value)
    changed["decision"]["zero_threshold"] = 0.6
    with pytest.raises(ValueError, match="already sealed"):
        Seal(tmp_path / "registry", changed).acquire()


@pytest.mark.parametrize("when", ["before", "during"])
def test_file_changes_prevent_forward_or_fail_its_attempt(tmp_path: Path, when: str) -> None:
    value = identity(tmp_path)
    seal = Seal(tmp_path / "registry", value)
    seal.acquire()
    path = Path(next(iter(value["files_sha256"])))
    calls = []

    def operation() -> None:
        calls.append(True)
        path.write_bytes(b"changed")

    if when == "before":
        path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="sealed file changed"):
        seal.forward(operation)
    assert bool(calls) == (when == "during")


def test_absent_cache_appearing_after_seal_is_rejected(tmp_path: Path) -> None:
    value = identity(tmp_path)
    absent = tmp_path / "absent.json"
    value["files_sha256"][str(absent)] = None
    seal = Seal(tmp_path / "registry", value)
    seal.acquire()
    absent.write_text("{}")
    with pytest.raises(ValueError, match="absent bound"):
        seal.verify()


def test_caller_mutation_cannot_change_frozen_identity(tmp_path: Path) -> None:
    value = identity(tmp_path)
    seal = Seal(tmp_path / "registry", value)
    seal.acquire()
    value["decision"]["patch_size"] = 120
    seal.verify()
    seal.identity["decision"]["patch_size"] = 120
    with pytest.raises(ValueError, match="contract changed"):
        seal.verify()


def test_seal_is_required_and_its_file_cannot_be_replaced(tmp_path: Path) -> None:
    seal = Seal(tmp_path / "registry", identity(tmp_path))
    with pytest.raises(ValueError, match="missing"):
        seal.forward(lambda: 1)
    seal.acquire()
    record = A.read_json(seal.path)
    record["created_utc"] = "tampered"
    A.write_json(seal.path, record)
    with pytest.raises(ValueError, match="changed"):
        seal.forward(lambda: 1)


@pytest.mark.parametrize("same", [False, True])
def test_racing_publishers_never_overwrite_a_different_contract(tmp_path: Path, same: bool) -> None:
    value = identity(tmp_path)
    second = copy.deepcopy(value)
    if not same:
        second["decision"]["zero_threshold"] = 0.6
    barrier = Barrier(2)

    def publish(item: JsonDict) -> str:
        seal = Seal(tmp_path / "registry", item)
        barrier.wait()
        try:
            seal.acquire()
            return "passed"
        except ValueError:
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(publish, [value, second]))
    assert results.count("passed") == (2 if same else 1)
    assert len(list((tmp_path / "registry").rglob("seal.json"))) == 1
    assert not list((tmp_path / "registry").rglob(".*.json"))


@pytest.mark.parametrize("mutation", ["unknown", "split", "fingerprint", "model", "relative"])
def test_invalid_contract_rejected_before_creation(tmp_path: Path, mutation: str) -> None:
    value = identity(tmp_path)
    if mutation == "unknown":
        value["extra"] = True
    elif mutation == "split":
        value["split"] = "test"
    elif mutation == "fingerprint":
        value["cohort_fingerprint"] = "../escape"
    elif mutation == "relative":
        value["files_sha256"] = {"relative.bin": "digest"}
    else:
        value["model"] = {}
    with pytest.raises(ValueError):
        Seal(tmp_path / "registry", value)
    assert not (tmp_path / "registry").exists()


def test_development_attempt_never_marks_confirmation_test_open(tmp_path: Path) -> None:
    value = identity(tmp_path)
    value["split"] = "validation"
    seal = Seal(tmp_path / "development", value)
    seal.acquire()
    seal.forward(lambda: 7)
    attempt = A.read_json(next((seal.path.parent / "attempts").glob("*.json")))
    assert attempt["test_opened"] is False and attempt["split"] == "validation"
