"""Version development identities after input-scope exclusions, preserving old evidence."""

from __future__ import annotations

import hashlib
import io
import json
import time
from collections import Counter
from pathlib import Path

import numpy as np
from Crypto.Hash import MD4
from PIL import Image

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline.confirmation import UnityConfirmationCohort as Cohort
from reproductions.unity_search_baseline.confirmation_revision import UnityConfirmationRevision


class UnityDevelopmentRevision:
    """Select replacements without using labels and bind both revised and supplemental lists."""

    def __init__(self, root: Path, config_path: Path) -> None:
        self.root = root.resolve()
        self.path = config_path.resolve()
        self.config_sha = A.sha256_file(self.path)
        self.config = A.read_json(self.path)
        self.output = Path(self.config["output"]).resolve()
        self.report = Path(self.config["report"]).resolve()
        self.project = Path(self.config["project"]).resolve()
        if not self.output.is_relative_to(self.root / "experiment report/.local"):
            raise ValueError("Revision artifacts must remain in local experiment storage")
        if not self.report.is_relative_to(self.root / "experiment report") or (
            self.report.is_relative_to(self.root / "experiment report/.local")
        ):
            raise ValueError("Revision report must remain in public experiment storage")
        if self.output.exists() or self.report.exists():
            raise FileExistsError("Use a new revision identity; preserve prior data")
        if self.config["expected_replacements"] != {"train": 13, "validation": 5}:
            raise ValueError("This revision requires the explicitly approved 13/5 replacements")

    def frozen(self, binding: JsonDict) -> JsonDict:
        path = Path(binding["path"])
        if A.sha256_file(path) != binding["sha256"]:
            raise ValueError(f"Revision input changed: {path}")
        return A.read_json(path)

    def claim_outputs(self) -> None:
        self.report.parent.mkdir(parents=True, exist_ok=True)
        with self.report.open("x", encoding="utf-8") as stream:
            json.dump({"status": "reserving", "config_sha256": self.config_sha}, stream)
        self.output.mkdir(parents=True, exist_ok=False)

    @staticmethod
    def key(path: str) -> str:
        return Cohort.asset_path(path).casefold()

    @staticmethod
    def replace_rows(
        original: dict[str, list[JsonDict]],
        removed: dict[str, set[str]],
        replacements: dict[str, list[JsonDict]],
    ) -> tuple[dict[str, list[JsonDict]], list[JsonDict]]:
        revised = {split: list(rows) for split, rows in original.items()}
        mappings: list[JsonDict] = []
        for split in ["train", "validation"]:
            indexes = [
                index
                for index, row in enumerate(original[split])
                if UnityDevelopmentRevision.key(row["path"]) in removed[split]
            ]
            if len(indexes) != len(removed[split]) or len(indexes) != len(replacements[split]):
                raise ValueError("Replacement count or original membership changed")
            for index, replacement in zip(indexes, replacements[split], strict=True):
                mappings.append(
                    {
                        "split": split,
                        "index": index,
                        "old_path": original[split][index]["path"],
                        "new_path": replacement["path"],
                    }
                )
                revised[split][index] = replacement
        identities = [
            UnityDevelopmentRevision.key(row["path"]) for rows in revised.values() for row in rows
        ]
        if len(identities) != len(set(identities)):
            raise ValueError("Revision introduced duplicate or cross-split assets")
        return revised, mappings

    def inspect(self, row: JsonDict) -> tuple[JsonDict | None, str | None]:
        path = (self.project / row["path"]).resolve()
        if not path.is_relative_to(self.project / "Assets"):
            raise ValueError("Candidate escapes project Assets")
        meta = Path(str(path) + ".meta")
        if not path.is_file() or not meta.is_file():
            return None, "missing_source_or_meta"
        if path.suffix.lower() in {".hdr", ".exr"}:
            return None, "HDR_source"
        metadata_bytes = meta.read_bytes()
        metadata = metadata_bytes.decode("utf-8-sig")
        shape = UnityConfirmationRevision.metadata_integer(metadata, "textureShape")
        kind = UnityConfirmationRevision.metadata_integer(metadata, "textureType")
        if shape != 1 or kind not in {0, 1, 8}:
            return None, "not_explicit_Default_Sprite_NormalMap_Tex2D"
        content = path.read_bytes()
        if MD4.new(content).hexdigest() != row["fileHash"]:
            return None, "source_md4_changed"
        try:
            with Image.open(io.BytesIO(content)) as image:
                pixels = np.asarray(image.convert("RGBA"), dtype=np.uint8)
                width, height = image.size
        except (OSError, ValueError):
            return None, "source_unreadable"
        return {
            **row,
            "width": width,
            "height": height,
            "alpha_nonopaque": bool(np.any(pixels[:, :, 3] != 255)),
            "source_sha256": hashlib.sha256(content).hexdigest(),
            "source_bytes": len(content),
            "meta_sha256": hashlib.sha256(metadata_bytes).hexdigest(),
            "texture_shape_metadata": shape,
            "texture_type_metadata": kind,
        }, None

    def reserve(self) -> JsonDict:
        started = time.perf_counter()
        source = self.frozen(self.config["source_manifest"])
        corpus = self.frozen(self.config["development_corpus"])
        issue = self.frozen(self.config["scope_audit"])
        snapshot = self.frozen(self.config["snapshot"])
        confirmation = self.frozen(self.config["confirmation_manifest"])
        if issue["out_of_scope_counts"] != self.config["expected_replacements"]:
            raise ValueError("Scope exclusions differ from the user-approved counts")
        removed = {split: set() for split in ["train", "validation"]}
        for row in issue["out_of_scope_rows"]:
            removed[row["split"]].add(self.key(row["path"]))
        for split, count in {"train": 10000, "validation": 1000}.items():
            if len(source["splits"][split]) != count or corpus["counts"][split] != count:
                raise ValueError("Original development coverage changed")
            original = [self.key(row["path"]) for row in source["splits"][split]]
            if original != [self.key(row["path"]) for row in corpus["splits"][split]]:
                raise ValueError("Original corpus and source order differ")
            cube = {
                self.key(row["path"])
                for row in corpus["splits"][split]
                if row["import_metadata"]["texture_dimension"] == "Cube"
            }
            if cube != removed[split]:
                raise ValueError("Exclusions must be exactly the approved Cube rows")
        assets: set[str] = set()
        groups: set[str] = set()
        hashes: set[str] = set()
        excluded_rows = [row for rows in source["splits"].values() for row in rows]
        for binding in self.config["excluded_manifests"]:
            excluded_rows.extend(
                row for rows in self.frozen(binding)["splits"].values() for row in rows
            )
        excluded_rows.extend([*confirmation["primary"], *confirmation["reserves"]])
        for row in excluded_rows:
            assets.add(self.key(row["path"]))
            groups.add(Cohort.asset_group(Cohort.asset_path(row["path"])))
            hashes.add(row["fileHash"].lower())
        candidates: list[JsonDict] = []
        exclusions: Counter[str] = Counter()
        for name, row in snapshot["entries"].items():
            if name.replace("\\", "/").split("/", 1)[0].casefold() != "assets":
                continue
            path = Cohort.asset_path(name)
            key, group, digest = self.key(path), Cohort.asset_group(path), row["fileHash"].lower()
            if key in assets or group in groups or digest in hashes:
                exclusions["historical_or_reserved_identity"] += 1
                continue
            rank = hashlib.sha256(
                f"unity-development-scope-v2|{self.config['seed']}|{key}".encode()
            ).hexdigest()
            candidates.append(
                {
                    "path": path,
                    "fileHash": digest,
                    "group": group,
                    "rank": rank,
                    "snapshot_key": name,
                }
            )
        candidates.sort(key=lambda row: (row["rank"], row["path"]))
        selected: list[JsonDict] = []
        rejected: list[JsonDict] = []
        for candidate in candidates:
            if candidate["group"] in groups or candidate["fileHash"] in hashes:
                exclusions["duplicate_replacement_group_or_source"] += 1
                continue
            inspected, reason = self.inspect(candidate)
            if inspected is None:
                exclusions[str(reason)] += 1
                rejected.append({"path": candidate["path"], "reason": reason})
                continue
            # Historical blockSize is carried only for the existing capture manifest schema.
            # It has no role in eligibility, ranking, split assignment, or native labels.
            inspected["blockSize"] = snapshot["entries"][candidate["snapshot_key"]]["blockSize"]
            selected.append(inspected)
            groups.add(inspected["group"])
            hashes.add(inspected["fileHash"])
            if len(selected) == 18:
                break
        if len(selected) != 18:
            raise ValueError("Not enough scope-compatible unseen replacement identities")
        replacements = {"train": selected[:13], "validation": selected[13:]}
        revised, mappings = self.replace_rows(source["splits"], removed, replacements)
        for binding in [
            self.config[key]
            for key in [
                "source_manifest",
                "development_corpus",
                "scope_audit",
                "snapshot",
                "confirmation_manifest",
            ]
        ]:
            self.frozen(binding)
        if A.sha256_file(self.path) != self.config_sha:
            raise ValueError("Revision configuration changed")
        for row in selected:
            path = self.project / row["path"]
            if A.sha256_file(path) != row["source_sha256"] or (
                A.sha256_file(Path(str(path) + ".meta")) != row["meta_sha256"]
            ):
                raise ValueError("Replacement source or import settings changed during reservation")
        self.claim_outputs()
        common = {
            "image_root": str(self.project),
            "config_sha256": self.config_sha,
            "source_snapshot_sha256": self.config["snapshot"]["sha256"],
            "scope": "V2 development input-scope revision; no quality-based selection",
        }
        files = {}
        for name, splits in [("manifest", revised), ("replacements", replacements)]:
            document = {
                **common,
                "splits": splits,
                "sizes": {split: len(rows) for split, rows in splits.items()},
            }
            document["fingerprint"] = A.fingerprint(document)
            path = self.output / f"{name}.json"
            A.write_json(path, document)
            files[name] = {"path": str(path), "sha256": A.sha256_file(path)}
        result = {
            "status": "reserved",
            "config_sha256": self.config_sha,
            "files": files,
            "replacements": mappings,
            "counts": {split: len(revised[split]) for split in replacements},
            "replacement_counts": {split: len(rows) for split, rows in replacements.items()},
            "replacement_groups": len({row["group"] for row in selected}),
            "selection": "SHA256(seed,path), first 13 train then 5 validation; unique groups",
            "selection_uses_quality_or_labels": False,
            "exclusions": dict(exclusions),
            "rejected_sources": rejected,
            "original_data_modified": False,
            "native_capture_complete": False,
            "test_opened": False,
            "training_updates": 0,
            "source_sha256": A.sha256_file(Path(__file__)),
            "wall_seconds": time.perf_counter() - started,
        }
        A.write_json(self.report, result)
        return result
