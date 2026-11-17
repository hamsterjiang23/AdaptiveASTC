"""Create explicit immutable development jobs for the approved V3 experiment matrix."""

from __future__ import annotations

from pathlib import Path

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline.v3_experiment import UnityV3Experiment


class UnityV3Configurations:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.experiment = UnityV3Experiment(root)
        self.public = self.experiment.output
        self.private = self.experiment.private

    def save(self, name: str, config: JsonDict) -> Path:
        path = self.public / f"{name}-config.json"
        if path.exists():
            if A.read_json(path) != config:
                raise FileExistsError(f"Existing configuration differs: {name}")
        else:
            A.write_json(path, config)
        return path

    def benchmark(
        self,
        *,
        smoke: bool,
        name: str | None = None,
        checkpoint: Path | None = None,
        input_modes: list[str] | None = None,
    ) -> Path:
        name = name or ("benchmark-smoke8-v1" if smoke else "benchmark-v2-full1000-v1")
        manifest = self.private / (
            "source-manifest-smoke.json" if smoke else "source-manifest.json"
        )
        source = A.read_json(manifest)
        if source["status"] != "passed":
            raise ValueError("Source manifest must pass before benchmark configuration")
        cases = []
        modes = input_modes or ["unity", "source_native", "source_aligned"]
        for grid in ["full20", "no_exhaustive16"]:
            if checkpoint is None:
                cases.extend(
                    {
                        "name": f"{arm}-{grid}",
                        "arm": arm,
                        "input_mode": "unity",
                        "candidate_set": grid,
                    }
                    for arm in ["original", "fixed8"]
                )
            cases.extend(
                {
                    "name": f"{arm}-{mode}-{grid}",
                    "arm": arm,
                    "input_mode": mode,
                    "candidate_set": grid,
                }
                for mode in modes
                for arm in ["pure", "forward"]
            )
        files = [
            "reproductions/unity_search_baseline/v3_benchmark.py",
            "reproductions/unity_search_baseline/v3_deployment.py",
            "reproductions/unity_search_baseline/v3_policy.py",
            "reproductions/unity_search_baseline/v3_evidence.py",
            "reproductions/unity_search_baseline/v3_experiment.py",
            "src/adaptive_astc/data/unity_v3_input.py",
            "src/adaptive_astc/data/unity_inference.py",
            "src/adaptive_astc/evaluation/unity_inference.py",
            "src/adaptive_astc/evaluation/unity_quality.py",
            "src/adaptive_astc/models/unity_quality.py",
            "reproductions/unity_search_baseline/supplement.py",
            "reproductions/unity_search_baseline/quality.py",
            "reproductions/unity_search_baseline/policy.py",
            "script/run_unity_v3.py",
        ]
        config: JsonDict = {
            "schema": "unity-v3-benchmark-v1",
            "smoke": smoke,
            "source_manifest": {"path": str(manifest), "sha256": A.sha256_file(manifest)},
            "cases": cases,
            "warmups": 1,
            "repetitions": 1 if smoke else 3,
            "scopes": ["files", "pixels_ready"],
            "measurement_modes": ["batch", "single"],
            "output": str(self.private / name),
            "report": str(self.public / f"{name}.json"),
            "execution_sources_sha256": {file: A.sha256_file(self.root / file) for file in files},
            "confirmation_execution_authorized": False,
        }
        if checkpoint is not None:
            config.update(checkpoint=str(checkpoint), checkpoint_sha256=A.sha256_file(checkpoint))
        return self.save(name, config)

    def training(self, *, mode: str, stage: str, smoke: bool, attempt: int = 1) -> Path:
        suffix = "smoke" if smoke else "full"
        name = f"train-{mode}-{stage}-{suffix}-v{attempt}"
        base = (
            self.root / "experiment report/unity-v2-20261112/imagenet-resnet34-full30-config.json"
        )
        manifest = self.private / (
            "source-manifest-smoke.json" if smoke else "source-manifest.json"
        )
        config: JsonDict = {
            "schema": "unity-v3-training-v1",
            "base_training_config": {"path": str(base), "sha256": A.sha256_file(base)},
            "source_manifest": {"path": str(manifest), "sha256": A.sha256_file(manifest)},
            "input_mode": mode,
            "smoke": smoke,
            "output": str(self.private / name),
            "report": str(self.public / f"{name}.json"),
        }
        if smoke:
            corpus = self.experiment.prepare_smoke_corpus()
            config.update(
                corpus=str(corpus), corpus_sha256=A.sha256_file(corpus / "corpus.json"), epochs=2
            )
        if stage == "head":
            parent = self.public / f"train-{mode}-full-{suffix}-v{attempt}.json"
            config["training_report"] = {"path": str(parent), "sha256": A.sha256_file(parent)}
        return self.save(name, config)
