"""Reserve unseen asset groups before native model selection and test opening."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path, PurePosixPath
from time import perf_counter

from Crypto.Hash import MD4

from adaptive_astc.config import JsonDict
from adaptive_astc.data import splitting
from adaptive_astc.data.splitting import DatasetSplitter
from adaptive_astc.utils.artifacts import ArtifactStore as A


class UnityConfirmationCohort:
    """Reserve identities only; imported pixels, native labels and evaluation remain sealed."""

    def __init__(self, root: Path, config: Path) -> None:
        self.root = root.resolve()
        self.config_path = config.resolve()
        self.config_sha = A.sha256_file(self.config_path)
        self.config = A.read_json(self.config_path)
        self.output = Path(self.config["output"]).resolve()
        self.report = Path(self.config["report"]).resolve()
        self.images = self.config["images"]
        self.reserves = self.config["reserves"]
        self.minimum_groups = self.config["minimum_groups"]
        if any(type(v) is not int or v < 1 for v in [self.images, self.minimum_groups]):
            raise ValueError("Positive image and group counts required")
        if type(self.reserves) is not int or self.reserves < 0:
            raise ValueError("Nonnegative reserve count required")
        if not self.config["excluded_manifests"] or type(self.config["seed"]) is not int:
            raise ValueError("Historical exclusions and integer seed required")
        if not self.output.is_relative_to(self.root / "experiment report/.local"):
            raise ValueError("Candidate identities belong under experiment report/.local")
        if not self.report.is_relative_to(
            self.root / "experiment report"
        ) or self.report.is_relative_to(self.root / "experiment report/.local"):
            raise ValueError("Report belongs under experiment report")
        if self.minimum_groups > self.images:
            raise ValueError("Minimum groups cannot exceed primary image count")
        if self.output.exists() or self.report.exists():
            raise FileExistsError("Confirmation reservation cannot overwrite an existing identity")

    @staticmethod
    def asset_path(value: str) -> str:
        path = PurePosixPath(value.replace("\\", "/"))
        if (
            path.is_absolute()
            or len(path.parts) < 2
            or path.parts[0].casefold() != "assets"
            or ".." in path.parts
            or ":" in str(path)
        ):
            raise ValueError(f"Invalid project asset path: {value}")
        return str(PurePosixPath("Assets", *path.parts[1:]))

    def verify_inputs(self) -> None:
        if A.sha256_file(self.config_path) != self.config_sha:
            raise ValueError("Reservation config changed")
        for record in [self.config["snapshot"], *self.config["excluded_manifests"]]:
            if A.sha256_file(Path(record["path"])) != record["sha256"]:
                raise ValueError(f"Reservation input changed: {record['path']}")

    @staticmethod
    def asset_group(path: str) -> str:
        parts = list(PurePosixPath(path).parts)
        categories = {
            "characters": "Characters",
            "monster": "Monster",
            "environment": "Environment",
        }
        if len(parts) >= 3 and parts[1].casefold() == "art" and parts[2].casefold() in categories:
            parts[:3] = ["Assets", "Art", categories[parts[2].casefold()]]
        return DatasetSplitter.asset_group(str(PurePosixPath(*parts))).casefold()

    def reserve(self) -> JsonDict:
        started = perf_counter()
        self.verify_inputs()
        image_root = Path(self.config["image_root"]).resolve()
        assets: set[str] = set()
        groups: set[str] = set()
        hashes: set[str] = set()
        for record in self.config["excluded_manifests"]:
            source = A.read_json(Path(record["path"]))
            for rows in source["splits"].values():
                for row in rows:
                    path = self.asset_path(row["path"])
                    assets.add(path.casefold())
                    groups.add(self.asset_group(path))
                    hashes.add(row["fileHash"].lower())
        entries = A.read_json(Path(self.config["snapshot"]["path"]))["entries"]
        candidates: list[JsonDict] = []
        excluded: Counter[str] = Counter()
        for name, record in entries.items():
            if name.replace("\\", "/").split("/", 1)[0].casefold() != "assets":
                excluded["outside_project_assets"] += 1
                continue
            path = self.asset_path(name)
            key = path.casefold()
            group = self.asset_group(path)
            digest = record["fileHash"].lower()
            if not re.fullmatch(r"[a-f0-9]{32}", digest):
                raise ValueError("Snapshot contains invalid source MD4")
            if group in groups:
                excluded["historical_group"] += 1
            elif key in assets:
                excluded["historical_asset"] += 1
            elif digest in hashes:
                excluded["historical_source_md4"] += 1
            else:
                rank = hashlib.sha256(
                    f"unity-confirmation-v1|{self.config['seed']}|{key}".encode()
                ).hexdigest()
                candidates.append({"path": path, "fileHash": digest, "group": group, "rank": rank})
        candidates.sort(key=lambda row: (row["rank"], row["path"]))
        self.report.parent.mkdir(parents=True, exist_ok=True)
        with self.report.open("x", encoding="utf-8") as claim:
            json.dump({"status": "reserving", "config_sha256": self.config_sha}, claim)
        self.output.mkdir(parents=True, exist_ok=False)
        selected: list[JsonDict] = []
        rejected: list[JsonDict] = []
        selected_paths: set[str] = set()
        selected_md4: set[str] = set()
        for row in candidates:
            path = (image_root / row["path"]).resolve()
            if not path.is_relative_to(image_root / "Assets"):
                raise ValueError("Resolved candidate escapes project Assets")
            meta = Path(str(path) + ".meta")
            reason: str | None = None
            if row["path"].casefold() in selected_paths or row["fileHash"] in selected_md4:
                reason = "duplicate_selected_identity"
            elif not path.is_file() or not meta.is_file():
                reason = "missing_source_or_meta"
            else:
                content = path.read_bytes()
                if MD4.new(content).hexdigest() != row["fileHash"]:
                    reason = "source_md4_changed"
                else:
                    row.update(
                        source_sha256=hashlib.sha256(content).hexdigest(),
                        source_bytes=len(content),
                        meta_sha256=A.sha256_file(meta),
                    )
            if reason:
                excluded[reason] += 1
                rejected.append({"path": row["path"], "reason": reason})
                continue
            selected.append(row)
            selected_paths.add(row["path"].casefold())
            selected_md4.add(row["fileHash"])
            if len(selected) == self.images + self.reserves:
                break
        self.verify_inputs()
        primary = selected[: self.images]
        primary_groups = len({row["group"] for row in primary})
        complete = (
            len(selected) == self.images + self.reserves and primary_groups >= self.minimum_groups
        )
        manifest = {
            "status": "reserved" if complete else "incomplete",
            "config_sha256": self.config_sha,
            "primary": primary,
            "reserves": selected[self.images :],
            "rejected": rejected,
            "test_opened": False,
            "native_pixels_audited": False,
            "native_labels_collected": False,
            "model_sealed": False,
        }
        manifest["fingerprint"] = A.fingerprint(manifest)
        A.write_json(self.output / "manifest.json", manifest)
        result = {
            "status": manifest["status"],
            "scope": "Unseen source identities only; not a completed native test corpus",
            "config_sha256": self.config_sha,
            "manifest": str(self.output / "manifest.json"),
            "manifest_sha256": A.sha256_file(self.output / "manifest.json"),
            "source_entries": len(entries),
            "eligible_before_file_checks": len(candidates),
            "historical_unique_assets": len(assets),
            "historical_unique_groups": len(groups),
            "primary_images": len(primary),
            "primary_groups": primary_groups,
            "reserve_images": len(selected[self.images :]),
            "exclusions": dict(excluded),
            "selection": "SHA256(seed,casefolded path); no compression label/quality filtering",
            "test_opened": False,
            "training_updates": 0,
            "native_pixels_audited": False,
            "native_labels_collected": False,
            "model_sealed": False,
            "source_sha256": A.sha256_file(Path(__file__)),
            "grouping_source_sha256": A.sha256_file(Path(splitting.__file__)),
            "wall_seconds": perf_counter() - started,
        }
        A.write_json(self.report, result)
        return result
