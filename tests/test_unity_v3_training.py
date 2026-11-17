"""CPU checks for paired inputs, original labels and immutable V3 training identities."""

from __future__ import annotations

import copy
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np
import pytest
import torch
from PIL import Image
from PIL import __version__ as pillow_version

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_patch_dataset import UnityPatchDataset
from adaptive_astc.data.unity_v3_dataset import UnityV3PatchDataset
from adaptive_astc.evaluation.unity_quality import UnityQualityPrediction, UnityTextureInput
from adaptive_astc.training.unity_v3_head import UnityV3HeadTrainer
from adaptive_astc.training.unity_v3_trainer import UnityV3Prediction, UnityV3Trainer
from adaptive_astc.utils.artifacts import ArtifactStore
from tests.test_unity_patch_dataset import DatasetFixture
from tests.test_unity_quality import measured_row, predictions
from tests.test_unity_search_policy import policy


class V3TrainingFixture:
    def __init__(self, root: Path, mode: str = "source_aligned") -> None:
        self.root = root
        self.native = DatasetFixture(root / "corpus")
        validation = copy.deepcopy(self.native.document["splits"]["train"][0])
        validation.update(path="Assets/validation.png", split="validation")
        validation["original_selection"]["asset"] = validation["path"]
        self.native.document["splits"]["validation"] = [validation]
        self.native.document["counts"]["validation"] = 1
        self.native.document["patch_counts"]["validation"] = 2
        self.native.publish()
        self.source = root / "source.png"
        pixels = np.zeros((6, 482, 4), dtype=np.uint8)
        pixels[:, :, 3] = np.arange(482, dtype=np.uint16) % 256
        Image.fromarray(pixels).save(self.source)
        self.manifest_path = root / "sources.json"
        self.manifest: JsonDict = {
            "status": "passed",
            "test_opened": False,
            "smoke": True,
            "pillow": pillow_version,
            "failures": [],
            "binding_sources_sha256": {},
            "splits": {
                split: [
                    {
                        "asset": row["path"],
                        "split": split,
                        "index": 1000,
                        "source": str(self.source),
                        "source_sha256": ArtifactStore.sha256_file(self.source),
                        "source_width": 482,
                        "source_height": 6,
                        "target_width": row["width"],
                        "target_height": row["height"],
                        "srgb": False,
                        "normal": False,
                        "need_alpha": True,
                        "normal_metric_mips": 1,
                    }
                    for row in rows
                ]
                for split, rows in self.native.document["splits"].items()
            },
        }
        self.base_path = root / "v2-base.json"
        self.base: JsonDict = {
            "corpus": str(self.native.root),
            "corpus_sha256": ArtifactStore.sha256_file(self.native.path),
            "output": str(root / "original-output"),
            "report": str(root / "original-report.json"),
            "image_pooling": "mean",
            "backbone_name": "resnet34",
            "initialization": "pretrained",
            "pretrained_weights": str(root / "weights.pt"),
            "pretrained_weights_sha256": "c" * 64,
            "patience": 0,
        }
        self.path = root / "v3.json"
        self.options: JsonDict = {
            "schema": "unity-v3-training-v1",
            "base_training_config": {},
            "source_manifest": {},
            "input_mode": mode,
            "output": str(root / "experiment report/.local/v3-output"),
            "report": str(root / "v3-report.json"),
            "smoke": True,
            "epochs": 2,
        }
        self.publish()

    def publish(self) -> None:
        ArtifactStore.write_json(self.base_path, self.base)
        ArtifactStore.write_json(self.manifest_path, self.manifest)
        for key, path in (
            ("base_training_config", self.base_path),
            ("source_manifest", self.manifest_path),
        ):
            self.options[key] = {"path": str(path), "sha256": ArtifactStore.sha256_file(path)}
        ArtifactStore.write_json(self.path, self.options)

    def trainer(self) -> UnityV3Trainer:
        return UnityV3Trainer(self.path, self.root)


@pytest.mark.parametrize("mode", ["unity", "source_aligned"])
def test_paired_dataset_preserves_targets_and_uses_explicit_input_context(
    tmp_path: Path, mode: str
) -> None:
    fixture = V3TrainingFixture(tmp_path, mode)
    trainer = fixture.trainer()
    native = fixture.native.load()
    actual = trainer.build_dataset("train")
    assert actual.rows == native.rows
    np.testing.assert_array_equal(actual.targets, native.targets)
    np.testing.assert_array_equal(actual.boxes, native.boxes)
    torch.testing.assert_close(actual[1]["channel_log_mse"], native[1]["channel_log_mse"])
    inputs = trainer.decision_inputs(actual)
    if mode == "source_aligned":
        assert isinstance(actual, UnityV3PatchDataset)
        assert inputs[0].black_pixel_ratio == 1.0
        assert inputs[0].alpha_constant is False
        assert actual.rows[0]["black_pixel_ratio"] == 1 / 241
        assert actual.rows[0]["alpha_constant"] is True
        assert actual.fingerprint != native.fingerprint
        assert not torch.equal(actual[0]["rgba"], native[0]["rgba"])
        actual.verify_sources()
    else:
        assert isinstance(actual, UnityPatchDataset)
        assert inputs == [UnityTextureInput.from_row(row) for row in native.rows]
        torch.testing.assert_close(actual[0]["rgba"], native[0]["rgba"], rtol=0, atol=0)
    assert trainer.config.epochs == 2
    assert trainer.config.image_batch_size == 16
    assert trainer.config.seed == 20261112


@pytest.mark.parametrize("part", ["wrapper", "base", "manifest", "source"])
def test_bound_training_inputs_cannot_change_after_preparation(tmp_path: Path, part: str) -> None:
    fixture = V3TrainingFixture(tmp_path)
    trainer = fixture.trainer()
    paths = {
        "wrapper": fixture.path,
        "base": fixture.base_path,
        "manifest": fixture.manifest_path,
        "source": fixture.source,
    }
    with paths[part].open("ab") as handle:
        handle.write(b" ")
    with pytest.raises(ValueError, match="changed"):
        trainer.verify_bindings()


@pytest.mark.parametrize(
    "field,value",
    [
        ("input_mode", "source_native"),
        ("schema", "legacy"),
        ("smoke", 1),
        ("corpus", "unbound-corpus"),
        ("unexpected", True),
    ],
)
def test_unrecognized_or_unbound_training_contract_rejected(
    tmp_path: Path, field: str, value: object
) -> None:
    fixture = V3TrainingFixture(tmp_path)
    fixture.options[field] = value
    fixture.publish()
    with pytest.raises(ValueError, match="V3 training contract"):
        fixture.trainer()


@pytest.mark.parametrize(
    "field,value",
    [
        ("backbone_name", "resnet18"),
        ("image_pooling", "mean_max"),
        ("patches_per_image", 2),
        ("train_image_indices", [0]),
        ("ema_decay", 0.9),
        ("selection_metric", "near_rmse"),
    ],
)
def test_paired_recipe_cannot_silently_change(tmp_path: Path, field: str, value: object) -> None:
    fixture = V3TrainingFixture(tmp_path)
    fixture.base[field] = value
    fixture.publish()
    with pytest.raises(ValueError, match="paired ResNet34"):
        fixture.trainer()


def test_formal_training_requires_full_epoch_budget(tmp_path: Path) -> None:
    fixture = V3TrainingFixture(tmp_path)
    fixture.options["smoke"] = False
    fixture.manifest["smoke"] = False
    fixture.publish()
    with pytest.raises(ValueError, match="paired ResNet34"):
        fixture.trainer()


@pytest.mark.parametrize("reason", ["failures", "test_opened", "pillow", "extra_split"])
def test_incomplete_or_unpinned_source_manifest_rejected(tmp_path: Path, reason: str) -> None:
    fixture = V3TrainingFixture(tmp_path)
    if reason == "failures":
        fixture.manifest["failures"] = [{"source": "missing.png"}]
    elif reason == "test_opened":
        fixture.manifest["test_opened"] = True
    elif reason == "pillow":
        fixture.manifest["pillow"] = "0.0"
    else:
        fixture.manifest["splits"]["confirmation"] = []
    fixture.publish()
    with pytest.raises(ValueError, match="development-only source manifest"):
        fixture.trainer()


def test_cross_split_source_asset_rejected(tmp_path: Path) -> None:
    fixture = V3TrainingFixture(tmp_path)
    fixture.manifest["splits"]["validation"][0]["asset"] = "ASSETS\\TRAIN.png"
    fixture.publish()
    with pytest.raises(ValueError, match="duplicated or crosses"):
        fixture.trainer()


def test_missing_source_pair_does_not_shrink_dataset(tmp_path: Path) -> None:
    fixture = V3TrainingFixture(tmp_path)
    fixture.manifest["splits"]["train"][0]["asset"] = "Assets/replacement.png"
    fixture.publish()
    with pytest.raises(ValueError, match="cover exactly"):
        fixture.trainer().build_dataset("train")


@pytest.mark.parametrize("field,value", [("target_width", 100), ("srgb", True)])
def test_import_config_must_match_supervision(tmp_path: Path, field: str, value: object) -> None:
    fixture = V3TrainingFixture(tmp_path)
    fixture.manifest["splits"]["train"][0][field] = value
    fixture.publish()
    with pytest.raises(ValueError, match="import settings do not match"):
        fixture.trainer().build_dataset("train")


def test_native_supervision_sha_remains_mandatory(tmp_path: Path) -> None:
    fixture = V3TrainingFixture(tmp_path)
    trainer = fixture.trainer()
    with fixture.native.target.open("ab") as handle:
        handle.write(b"changed")
    with pytest.raises(ValueError, match="Frozen Unity targets changed"):
        trainer.build_dataset("train")
    with pytest.raises(ValueError, match="confirmation"):
        trainer.build_dataset("confirmation")


@pytest.mark.parametrize("normal,srgb", [(False, True), (False, False), (True, False)])
def test_unity_input_scoring_matches_frozen_v2(normal: bool, srgb: bool) -> None:
    row = measured_row(normal=normal, srgb=srgb)
    mse, zero, quality = predictions(row)
    expected, old_rows = UnityQualityPrediction.score(
        [row], [policy()], mse[None], zero[None], quality[None]
    )
    actual, new_rows = UnityV3Prediction.score(
        [row],
        [policy()],
        mse[None],
        zero[None],
        quality[None],
        [UnityTextureInput.from_row(row)],
    )
    expected.pop("scope")
    actual.pop("scope")
    assert actual == expected
    for old, new in zip(old_rows, new_rows, strict=True):
        assert new.pop("prediction_input") == asdict(UnityTextureInput.from_row(row))
        assert new.pop("quality_reference_input") == asdict(UnityTextureInput.from_row(row))
        assert new == old


def test_source_black_ratio_changes_start_but_true_quality_uses_unity_threshold() -> None:
    row = measured_row()
    row["image_quality"][0].update(psnr=32.0, ms_ssim_db=24.0)
    native = UnityTextureInput.from_row(row)
    truth = [
        {"block": b, "preset": p, "metrics": q}
        for (b, p), q in zip(UnityQualityPrediction.GRID, row["image_quality"], strict=True)
    ]
    row["original_selection"] = asdict(
        policy().select(truth, width=240, height=240, srgb=True, normal=False)
    )
    mse, zero, quality = predictions(row)
    source = replace(native, black_pixel_ratio=1.0)
    # Exact Unity errors would move the source-based start to the best PSNR fallback.
    _, source_rows = UnityV3Prediction.score(
        [row], [policy()], mse[None], zero[None], quality[None], [source]
    )
    assert source_rows[0]["predicted_decision"]["selected_index"] == 10
    assert source_rows[0]["original_decision"]["selected_index"] == 0
    assert source_rows[0]["prediction_input"]["black_pixel_ratio"] == 1.0
    assert source_rows[0]["quality_reference_input"]["black_pixel_ratio"] == 0.0
    # A forecast of38dB selects0 even under the source37dB threshold. Actual32dB
    # still passes the native30dB gate: source statistics cannot redefine truth.
    mse[0] = 10 ** (-38.0 / 10)
    metrics, observations = UnityV3Prediction.score(
        [row], [policy()], mse[None], zero[None], quality[None], [source]
    )
    assert observations[0]["predicted_decision"]["effective_psnr_threshold"] == 37.0
    assert observations[0]["original_decision"]["effective_psnr_threshold"] == 30.0
    assert observations[0]["actual_strict_quality_met"] is True
    assert metrics["accuracy"] == 1.0


def test_source_alpha_statistics_affect_only_prediction_channel_selection() -> None:
    row = measured_row(srgb=False)
    mse, zero, quality = predictions(row)
    mse[0, :3] = 1e-4
    mse[0, 3] = 1.0
    native = UnityTextureInput.from_row(row)
    source = replace(native, alpha_constant=False)
    _, native_rows = UnityV3Prediction.score(
        [row], [policy()], mse[None], zero[None], quality[None], [native]
    )
    _, source_rows = UnityV3Prediction.score(
        [row], [policy()], mse[None], zero[None], quality[None], [source]
    )
    assert native_rows[0]["predicted_decision"]["selected_index"] == 0
    assert native_rows[0]["actual_strict_quality_met"] is False
    assert source_rows[0]["predicted_decision"]["selected_index"] == 10
    assert source_rows[0]["quality_reference_input"]["alpha_constant"] is True
    assert source_rows[0]["actual_strict_quality_met"] is True


def test_prediction_context_must_cover_every_image() -> None:
    row = measured_row()
    mse, zero, quality = predictions(row)
    with pytest.raises(ValueError, match="cover each evaluation image"):
        UnityV3Prediction.score([row], [policy()], mse[None], zero[None], quality[None], [])


def test_failed_training_keeps_result_and_cannot_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = V3TrainingFixture(tmp_path)
    trainer = fixture.trainer()

    def fail(self: UnityV3Trainer, state: JsonDict, started: float) -> JsonDict:
        state["training_updates"] = 1
        raise RuntimeError("deliberate CPU failure before training")

    monkeypatch.setattr(UnityV3Trainer, "fit", fail)
    with pytest.raises(RuntimeError, match="deliberate CPU failure"):
        trainer.run()
    saved = ArtifactStore.read_json(trainer.config.report)
    assert saved["status"] == "failed"
    assert saved["training_updates"] == 1
    assert saved["test_opened"] is False
    before = trainer.config.report.read_bytes()
    with pytest.raises(FileExistsError):
        trainer.run()
    assert trainer.config.report.read_bytes() == before


def test_head_requires_full_stage_binding_before_any_gpu_work(tmp_path: Path) -> None:
    fixture = V3TrainingFixture(tmp_path)
    trainer = UnityV3HeadTrainer(fixture.path, fixture.root)
    with pytest.raises(ValueError, match="bound completed full-stage report"):
        trainer.run()
    assert not trainer.config.output.exists()
    assert not trainer.config.report.exists()
