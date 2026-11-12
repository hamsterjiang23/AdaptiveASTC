"""Version a reserved confirmation cohort using input eligibility, never quality labels."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from time import perf_counter

from Crypto.Hash import MD4
from PIL import Image

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline.confirmation import UnityConfirmationCohort


class UnityConfirmationRevision(UnityConfirmationCohort):
    """Retain primary positions and fill rejected slots in the original reserve order."""

    def verify_revision_inputs(self) -> tuple[JsonDict, JsonDict]:
        self.verify_inputs()
        for binding in self.config["prior"].values():
            if A.sha256_file(Path(binding["path"])) != binding["sha256"]:
                raise ValueError("Prior confirmation evidence changed")
        prior_config = A.read_json(Path(self.config["prior"]["config"]["path"]))
        prior_report = A.read_json(Path(self.config["prior"]["report"]["path"]))
        manifest_binding = self.config["prior"]["manifest"]
        manifest = A.read_json(Path(manifest_binding["path"]))
        fingerprint = manifest.pop("fingerprint")
        if (
            fingerprint != A.fingerprint(manifest)
            or manifest["status"] != "reserved"
            or prior_report["status"] != "reserved"
            or manifest["config_sha256"] != self.config["prior"]["config"]["sha256"]
            or prior_report["config_sha256"] != manifest["config_sha256"]
            or Path(prior_report["manifest"]).resolve() != Path(manifest_binding["path"]).resolve()
            or prior_report["manifest_sha256"] != manifest_binding["sha256"]
        ):
            raise ValueError("Prior reservation provenance is inconsistent")
        for key in ["snapshot", "excluded_manifests", "seed", "images", "minimum_groups"]:
            if self.config[key] != prior_config[key]:
                raise ValueError(f"Revision must preserve prior {key}")
        if Path(self.config["image_root"]).resolve() != Path(prior_config["image_root"]).resolve():
            raise ValueError("Revision changed the Unity project")
        if len(manifest["primary"]) != self.images:
            raise ValueError("Prior primary count is inconsistent")
        return manifest, prior_report

    @staticmethod
    def metadata_integer(text: str, key: str) -> int | None:
        matches = re.findall(rf"^  {re.escape(key)}:\s*(\d+)\s*$", text, re.MULTILINE)
        if len(matches) > 1:
            raise ValueError(f"Ambiguous importer metadata: {key}")
        return int(matches[0]) if matches else None

    def inspect(self, row: JsonDict) -> JsonDict:
        image_root = Path(self.config["image_root"]).resolve()
        path = (image_root / self.asset_path(row["path"])).resolve()
        if not path.is_relative_to(image_root / "Assets"):
            raise ValueError("Source escapes project Assets")
        content = path.read_bytes()
        meta = Path(str(path) + ".meta")
        if (
            MD4.new(content).hexdigest() != row["fileHash"]
            or hashlib.sha256(content).hexdigest() != row["source_sha256"]
            or len(content) != row["source_bytes"]
            or A.sha256_file(meta) != row["meta_sha256"]
        ):
            raise ValueError(f"Frozen asset changed: {row['path']}")
        metadata = meta.read_text(encoding="utf-8-sig")
        shape = self.metadata_integer(metadata, "textureShape")
        kind = self.metadata_integer(metadata, "textureType")
        reasons: list[str] = []
        if kind == 2:
            reasons.append("GUI")
        if shape == 2:
            reasons.append("Cube")
        if path.suffix.lower() in {".hdr", ".exr"}:
            reasons.append("HDR_source")
        # Legacy missing fields and textureType=5 are not guessed to be unsupported.
        # Actual imported Default/Sprite/NormalMap and Tex2D remain a post-capture gate.
        if not reasons and (shape not in {None, 1} or kind not in {None, 0, 1, 5, 8}):
            raise ValueError(f"Unapproved unsupported importer type: {row['path']}")
        dimensions: list[int] | None = None
        if not reasons:
            with Image.open(path) as source:
                rgb = source.convert("RGB")
                rgb.load()
                dimensions = list(rgb.size)
        return {
            "path": row["path"],
            "texture_shape_metadata": shape,
            "texture_type_metadata": kind,
            "exclusion_reasons": reasons,
            "source_rgb_readable": dimensions is not None,
            "source_dimensions": dimensions,
        }

    @staticmethod
    def replace(
        primary: list[JsonDict], reserves: list[JsonDict], rejected: set[str]
    ) -> tuple[list[JsonDict], list[JsonDict], list[JsonDict]]:
        eligible = [
            (index, row) for index, row in enumerate(reserves) if row["path"] not in rejected
        ]
        replacements: list[JsonDict] = []
        revised: list[JsonDict] = []
        for index, row in enumerate(primary):
            if row["path"] in rejected:
                if len(replacements) >= len(eligible):
                    raise ValueError("Not enough eligible original reserves")
                reserve_index, replacement = eligible[len(replacements)]
                replacements.append(
                    {
                        "primary_index": index,
                        "old_path": row["path"],
                        "new_path": replacement["path"],
                        "original_reserve_index": reserve_index,
                    }
                )
                revised.append(replacement)
            else:
                revised.append(row)
        remaining = [row for _, row in eligible[len(replacements) :]]
        return revised, remaining, replacements

    def revise(self) -> JsonDict:
        started = perf_counter()
        manifest, _ = self.verify_revision_inputs()
        original_rows = [*manifest["primary"], *manifest["reserves"]]
        if len({row["path"].casefold() for row in original_rows}) != len(original_rows):
            raise ValueError("Duplicate prior paths")
        if len({row["fileHash"] for row in original_rows}) != len(original_rows):
            raise ValueError("Duplicate prior source identities")
        inspections = [self.inspect(row) for row in original_rows]
        rejected = {row["path"] for row in inspections if row["exclusion_reasons"]}
        primary, reserves, replacements = self.replace(
            manifest["primary"], manifest["reserves"], rejected
        )
        if len(replacements) != self.config["expected_replacements"]:
            raise ValueError("Eligibility changes differ from the approved replacement count")
        if len(reserves) != self.reserves:
            raise ValueError("Remaining eligible reserve count differs from configuration")
        assets: set[str] = set()
        groups: set[str] = set()
        hashes: set[str] = set()
        for binding in self.config["excluded_manifests"]:
            for rows in A.read_json(Path(binding["path"]))["splits"].values():
                for row in rows:
                    assets.add(self.asset_path(row["path"]).casefold())
                    groups.add(self.asset_group(row["path"]))
                    hashes.add(row["fileHash"].lower())
        for row in [*primary, *reserves]:
            group = self.asset_group(row["path"])
            if (
                row["path"].casefold() in assets
                or group in groups
                or row["fileHash"].lower() in hashes
                or group != row["group"]
            ):
                raise ValueError("Revised identities overlap historical data or changed grouping")
        primary_groups = len({row["group"] for row in primary})
        if primary_groups < self.minimum_groups:
            raise ValueError("Insufficient revised asset groups")
        self.verify_revision_inputs()
        self.report.parent.mkdir(parents=True, exist_ok=True)
        with self.report.open("x", encoding="utf-8") as claim:
            json.dump({"status": "revising", "config_sha256": self.config_sha}, claim)
        self.output.mkdir(parents=True, exist_ok=False)
        audit = {
            "inspections": inspections,
            "replacements": replacements,
            "prior": self.config["prior"],
            "historical_asset_group_source_md4_overlaps": 0,
        }
        A.write_json(self.output / "revision-audit.json", audit)
        revised = {
            "status": "reserved",
            "config_sha256": self.config_sha,
            "primary": primary,
            "reserves": reserves,
            "rejected": [row for row in inspections if row["exclusion_reasons"]],
            "prior_manifest_sha256": self.config["prior"]["manifest"]["sha256"],
            "revision_audit_sha256": A.sha256_file(self.output / "revision-audit.json"),
            "test_opened": False,
            "native_pixels_audited": False,
            "native_labels_collected": False,
            "model_sealed": False,
        }
        revised["fingerprint"] = A.fingerprint(revised)
        A.write_json(self.output / "manifest.json", revised)
        reasons = Counter(
            reason for row in inspections[: self.images] for reason in row["exclusion_reasons"]
        )
        result = {
            "status": "reserved",
            "scope": "V2 source eligibility revision; native input validation still required",
            "config_sha256": self.config_sha,
            "manifest": str(self.output / "manifest.json"),
            "manifest_sha256": A.sha256_file(self.output / "manifest.json"),
            "revision_audit": str(self.output / "revision-audit.json"),
            "revision_audit_sha256": revised["revision_audit_sha256"],
            "prior": self.config["prior"],
            "primary_images": len(primary),
            "primary_groups": primary_groups,
            "reserve_images": len(reserves),
            "retained_primary": self.images - len(replacements),
            "replaced_primary": len(replacements),
            "primary_exclusion_reasons_overlapping": dict(reasons),
            "inspected_sources": len(inspections),
            "eligible_readable_sources": len(inspections) - len(rejected),
            "historical_asset_group_source_md4_overlaps": 0,
            "selection": "Preserve primary slots; consume eligible original reserves in order",
            "test_opened": False,
            "training_updates": 0,
            "native_pixels_audited": False,
            "native_labels_collected": False,
            "model_sealed": False,
            "sources_sha256": {
                name: A.sha256_file(Path(__file__).resolve().parents[2] / name)
                for name in [
                    "reproductions/unity_search_baseline/confirmation_revision.py",
                    "script/revise_unity_confirmation.py",
                ]
            },
            "wall_seconds": perf_counter() - started,
        }
        A.write_json(self.report, result)
        return result
