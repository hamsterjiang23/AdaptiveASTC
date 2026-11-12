"""Compare capture-only inputs to frozen development training tensors without a forward pass."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import torch

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_capture_input import UnityCaptureInputAdapter
from adaptive_astc.data.unity_patch_dataset import UnityPatchDataset
from adaptive_astc.evaluation.unity_quality import UnityTextureInput
from adaptive_astc.utils.artifacts import ArtifactStore as A


class UnityCaptureInputAudit:
    def __init__(self, root: Path, config: Path) -> None:
        self.root, self.path = root.resolve(), config.resolve()
        self.config_sha = A.sha256_file(self.path)
        self.config = A.read_json(self.path)

    @staticmethod
    def execution_sources(root: Path) -> dict[str, str]:
        files = [
            "src/adaptive_astc/data/unity_capture_input.py",
            "src/adaptive_astc/data/unity_inference.py",
            "src/adaptive_astc/data/unity_patch_dataset.py",
            "src/adaptive_astc/data/patch_targets.py",
            "src/adaptive_astc/evaluation/unity_quality.py",
            "src/adaptive_astc/utils/artifacts.py",
            "reproductions/unity_search_baseline/patch_targets.py",
            "reproductions/unity_search_baseline/supplement.py",
            "reproductions/unity_search_baseline/policy.py",
            "reproductions/unity_search_baseline/capture_input_audit.py",
            "script/audit_unity_capture_inputs.py",
        ]
        return {name: A.sha256_file(root / name) for name in files}

    def verify(self) -> None:
        if A.sha256_file(self.path) != self.config_sha:
            raise ValueError("Capture input audit configuration changed")
        if self.config["sources_sha256"] != self.execution_sources(self.root):
            raise ValueError("Capture input audit sources changed or are incomplete")
        if not self.config["corpora"]:
            raise ValueError("At least one frozen development corpus is required")
        for entry in self.config["corpora"]:
            if A.sha256_file(Path(entry["path"])) != entry["sha256"]:
                raise ValueError("Capture input audit corpus changed")

    def run(self) -> JsonDict:
        self.verify()
        report = Path(self.config["report"]).resolve()
        public = self.root / "experiment report"
        if not report.is_relative_to(public) or report.is_relative_to(public / ".local"):
            raise ValueError("Capture input report must be public")
        report.parent.mkdir(parents=True, exist_ok=True)
        with report.open("x", encoding="utf-8") as stream:
            stream.write("{}")
        started = time.perf_counter()
        state: JsonDict = {
            "status": "running",
            "config_sha256": self.config_sha,
            "source_files_sha256": self.config["sources_sha256"],
            "corpora": self.config["corpora"],
            "splits": [],
            "test_opened": False,
            "training_updates": 0,
            "model_forward_calls": 0,
            "scope": "Development tensor parity only; no independent confirmation evaluation",
        }
        old_threads = torch.get_num_threads()
        torch.set_num_threads(1)
        try:
            for entry in self.config["corpora"]:
                path = Path(entry["path"])
                document = A.read_json(path)
                for split in ["train", "validation"]:
                    if not document["splits"][split]:
                        continue
                    expected = UnityPatchDataset(
                        path.parent, split, expected_sha256=entry["sha256"]
                    )
                    if expected.patch_size != 240:
                        raise ValueError("Capture input audit requires Native240 training inputs")
                    # Explicit projection ensures no search/quality field can reach the adapter.
                    captures = [
                        {
                            "path": row["path"],
                            "source_split": row["split"],
                            "reference_png": row["reference"],
                            "reference_sha256": row["reference_sha256"],
                            "width": row["width"],
                            "height": row["height"],
                            "import_metadata": row["import_metadata"],
                            "actual_options": row["actual_options"],
                        }
                        for row in expected.rows
                    ]
                    adapter = UnityCaptureInputAdapter(captures, split)
                    actual = adapter.dataset()
                    for field in ["boxes", "image_ids", "pixel_counts", "input_metadata"]:
                        np.testing.assert_array_equal(
                            getattr(actual, field), getattr(expected, field)
                        )
                    if len(actual) != len(expected):
                        raise ValueError("Capture input patch coverage differs from training")
                    for index in range(len(actual)):
                        new_item, old_item = actual[index], expected[index]
                        for field, tensor in new_item.items():
                            torch.testing.assert_close(tensor, old_item[field], rtol=0, atol=0)
                    for row, decision in zip(expected.rows, adapter.decision_inputs, strict=True):
                        if decision != UnityTextureInput.from_row(row):
                            raise ValueError("Capture decision metadata differs from training")
                    adapter.verify_references()
                    state["splits"].append(
                        {
                            "corpus": str(path),
                            "split": split,
                            "images": len(captures),
                            "patches": len(actual),
                            "input_fingerprint": adapter.fingerprint,
                            "texture_types": sorted(
                                {row["texture_type"] for row in adapter.bindings}
                            ),
                            "normal_mip_counts": sorted(
                                {
                                    row["normal_metric_mips"]
                                    for row in adapter.bindings
                                    if row["normal"]
                                }
                            ),
                            "max_tensor_difference": 0.0,
                            "decision_inputs_equal": True,
                        }
                    )
                    A.write_json(report, state)
            self.verify()
            if not state["splits"]:
                raise ValueError("Capture input audit did not compare any development images")
            state["status"] = "passed"
        except BaseException as error:
            state.update(status="failed", error=repr(error))
            raise
        finally:
            torch.set_num_threads(old_threads)
            state["wall_seconds"] = time.perf_counter() - started
            A.write_json(report, state)
        return state
