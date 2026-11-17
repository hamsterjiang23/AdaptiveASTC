"""Bind V3 development evidence and source files without opening the confirmation set."""

from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from pathlib import Path

import PIL
import psutil
from Crypto.Hash import MD4
from PIL import Image

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore as A


class UnityV3Evidence:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.output = self.root / "experiment report/unity-v3-20261113"
        self.private = self.root / "experiment report/.local/unity-v3-20261113"
        self.plan = self.root / "experiment plan/V3"
        self.v2 = self.root / "experiment report/unity-v2-20261112"

    def prepare(self) -> JsonDict:
        self.output.mkdir(parents=True, exist_ok=True)
        self.private.mkdir(parents=True, exist_ok=True)
        report_path = self.plan / "evidence.json"
        if report_path.exists():
            existing = A.read_json(report_path)
            for name, digest in existing["files_sha256"].items():
                if A.sha256_file(Path(name)) != digest:
                    raise ValueError(f"Frozen V3 parent evidence changed: {name}")
            return existing
        filenames = [
            "imagenet-resnet34-head-sampled4.json",
            "imagenet-resnet34-head-sampled4-result.json",
            "imagenet-resnet34-full30-config.json",
            "imagenet-resnet34-head-sampled4-config.json",
            "forward-search-full1000-v1.json",
            "forward-search-validation-freeze.json",
            "confirmation-cohort-v3-result.json",
            "forward-system-protocol-readiness-v4.json",
        ]
        files = {str(self.v2 / name): A.sha256_file(self.v2 / name) for name in filenames}
        training = A.read_json(self.v2 / filenames[0])
        config = training["config"]
        corpus = Path(config["corpus"]) / "corpus.json"
        if A.sha256_file(corpus) != config["corpus_sha256"]:
            raise ValueError("Development corpus changed from V2 training")
        files[str(corpus)] = config["corpus_sha256"]
        artifacts: JsonDict = {}
        for name, digest in training["best_artifacts_sha256"].items():
            path = Path(config["output"]) / name
            if A.sha256_file(path) != digest:
                raise ValueError(f"Frozen model artifact changed: {name}")
            files[str(path)] = digest
            artifacts[name] = str(path)
        measured = A.read_json(self.v2 / "forward-search-full1000-v1.json")
        binaries: JsonDict = {}
        for name, digest in measured["inputs_sha256"].items():
            if name.endswith(".dll") or name.endswith("build-receipt.json"):
                if A.sha256_file(Path(name)) != digest:
                    raise ValueError(f"Native quality or encoding library changed: {name}")
                files[name] = digest
                binaries[Path(name).name] = name
        readiness = A.read_json(self.v2 / "forward-system-protocol-readiness-v4.json")
        if readiness["test_opened"] or readiness["formal_confirmation_executed"]:
            raise ValueError("Confirmation state changed; do not treat it as unopened")
        result = {
            "status": "passed_parent_binding",
            "corpus": str(corpus),
            "corpus_sha256": config["corpus_sha256"],
            "artifacts": artifacts,
            "binaries": binaries,
            "files_sha256": files,
            "counts": {"train": 10000, "validation": 1000},
            "reference_labels": "original_unity_canonical20",
            "validation_baseline": measured["summary"]["forward"]["validation_metrics"],
            "confirmation_execution_authorized": False,
            "test_opened": False,
            "confirmation_pixels_read": 0,
        }
        A.write_json(report_path, result)
        return result

    @staticmethod
    def smoke_indices(rows: list[JsonDict], count: int) -> list[int]:
        chosen: list[int] = []
        conditions = [
            lambda r: r["metadata"]["is_normal"],
            lambda r: not r["metadata"]["is_normal"] and not r["import_metadata"]["srgb"],
            lambda r: r["metadata"]["need_alpha"],
            lambda r: r["width"] * r["height"] >= 512**2,
            lambda r: r["width"] * r["height"] < 128**2,
            lambda r: r["import_metadata"]["texture_type"] == "Sprite",
        ]
        for condition in conditions:
            candidates = [i for i, row in enumerate(rows) if condition(row) and i not in chosen]
            if candidates:
                chosen.append(candidates[0])
        chosen += [i for i in range(len(rows)) if i not in chosen][: max(0, count - len(chosen))]
        return sorted(chosen[:count])

    def audit_sources(self, *, smoke: bool = False) -> JsonDict:
        started = time.perf_counter()
        evidence = self.prepare()
        suffix = "-smoke" if smoke else ""
        destination = self.private / f"source-manifest{suffix}.json"
        report = self.output / f"source-input-audit{suffix}.json"
        if report.exists() or destination.exists():
            raise FileExistsError("Source audit already has an identity; preserve it")
        document = A.read_json(Path(evidence["corpus"]))
        if document["counts"] != evidence["counts"] or set(document["splits"]) != {
            "train",
            "validation",
        }:
            raise ValueError("Development split differs from approved counts")
        project = Path(evidence["binaries"]["astcenc-avx2-shared.dll"]).parents[4]
        manifests: dict[str, JsonDict] = {}
        bound: dict[str, str] = {}
        rows: dict[str, list[JsonDict]] = {"train": [], "validation": []}
        failures: list[JsonDict] = []
        counts: Counter[str] = Counter()
        for split, originals in document["splits"].items():
            indices = (
                self.smoke_indices(originals, 32 if split == "train" else 8)
                if smoke
                else list(range(len(originals)))
            )
            for index in indices:
                row = originals[index]
                try:
                    source = row["source_shard"]
                    shard_path = Path(source["corpus"])
                    if str(shard_path) not in manifests:
                        if A.sha256_file(shard_path) != source["sha256"]:
                            raise ValueError("Source shard SHA changed")
                        shard = A.read_json(shard_path)
                        manifest_path = Path(shard["config"]["candidate_manifest"])
                        digest = shard["config"]["candidate_manifest_sha256"]
                        if A.sha256_file(manifest_path) != digest:
                            raise ValueError("Candidate manifest SHA changed")
                        manifests[str(shard_path)] = A.read_json(manifest_path)
                        bound[str(shard_path)] = source["sha256"]
                        bound[str(manifest_path)] = digest
                    original = manifests[str(shard_path)]["splits"][split][source["index"]]
                    if (
                        original["path"] != row["path"]
                        or original["reference_sha256"] != row["reference_sha256"]
                    ):
                        raise ValueError("Original source/Unity target identity differs")
                    path = (project / row["path"]).resolve()
                    if not path.is_relative_to(project):
                        raise ValueError("Source path leaves declared asset project")
                    raw = path.read_bytes()
                    md4 = MD4.new(raw).hexdigest()
                    if md4.lower() != original["source_md4"].lower():
                        raise ValueError("Source bytes changed since Unity capture")
                    with Image.open(path) as image:
                        image.load()
                        width, height = image.size
                        mode = image.mode
                        rgba = image.convert("RGBA")
                        rgba.load()
                    spec = {
                        "asset": row["path"],
                        "split": split,
                        "index": index,
                        "source": str(path),
                        "source_sha256": hashlib.sha256(raw).hexdigest(),
                        "source_md4": md4,
                        "source_width": width,
                        "source_height": height,
                        "target_width": row["width"],
                        "target_height": row["height"],
                        "srgb": row["import_metadata"]["srgb"],
                        "normal": row["metadata"]["is_normal"],
                        "need_alpha": row["metadata"]["need_alpha"],
                        "normal_metric_mips": row["metadata"]["mip_count"]
                        if row["metadata"]["is_normal"]
                        else 1,
                        "source_mode": mode,
                    }
                    rows[split].append(spec)
                    counts[f"{split}:decoded"] += 1
                    counts[f"{split}:size_changed"] += (width, height) != (
                        row["width"],
                        row["height"],
                    )
                    counts[f"{split}:normal"] += spec["normal"]
                    counts[f"format:{path.suffix.lower()}"] += 1
                except Exception as error:
                    failures.append(
                        {"split": split, "index": index, "asset": row["path"], "error": repr(error)}
                    )
                if (index + 1) % 500 == 0:
                    print(
                        json.dumps(
                            {
                                "stage": "source_audit",
                                "split": split,
                                "visited": index + 1,
                                "failures": len(failures),
                            }
                        ),
                        flush=True,
                    )
        status = "passed" if not failures else "failed"
        manifest = {
            "status": status,
            "smoke": smoke,
            "corpus_sha256": evidence["corpus_sha256"],
            "project": str(project),
            "pillow": PIL.__version__,
            "splits": rows,
            "binding_sources_sha256": bound,
            "failures": failures,
            "test_opened": False,
        }
        A.write_json(destination, manifest)
        result = {
            "status": status,
            "counts": dict(counts),
            "failures": failures,
            "manifest": str(destination),
            "manifest_sha256": A.sha256_file(destination),
            "source_hash_comparison": "MD4 bytes against each original capture candidate manifest",
            "wall_seconds": time.perf_counter() - started,
            "pillow": PIL.__version__,
            "available_memory_bytes": psutil.virtual_memory().available,
            "model_forward_calls": 0,
            "training_updates": 0,
            "test_opened": False,
        }
        A.write_json(report, result)
        return result
