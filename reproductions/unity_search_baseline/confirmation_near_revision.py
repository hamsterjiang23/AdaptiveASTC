"""Apply an approved near-identity revision while preserving frozen primary slots."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline.confirmation_revision import UnityConfirmationRevision


class UnityConfirmationNearRevision(UnityConfirmationRevision):
    """Reuse source eligibility checks and consume only explicitly approved reserves."""

    @staticmethod
    def approved_mapping(manifest: JsonDict, proposal: JsonDict) -> set[str]:
        replacements = proposal["proposed_replacements"]
        indices = [row["primary_index_zero_based"] for row in replacements]
        if (
            not replacements
            or any(type(index) is not int for index in indices)
            or indices != sorted(set(indices))
            or proposal["selection_uses_model_predictions_quality_or_native_labels"] is not False
            or proposal["model_forward_calls"] != 0
            or proposal["training_updates"] != 0
            or proposal["cohort_modified"] is not False
        ):
            raise ValueError("Require an ordered identity-only proposal")
        for index, row in enumerate(replacements):
            slot = row["primary_index_zero_based"]
            if (
                not 0 <= slot < len(manifest["primary"])
                or row["primary_position_one_based"] != slot + 1
                or row["reserve_position_one_based"] != index + 1
                or row["original"] != manifest["primary"][slot]
                or index >= len(manifest["reserves"])
                or row["replacement"] != manifest["reserves"][index]
            ):
                raise ValueError("Proposal changed primary identities or frozen reserve order")
        return {row["original"]["path"] for row in replacements}

    def verify_revision_inputs(self) -> tuple[JsonDict, JsonDict]:
        manifest, report = super().verify_revision_inputs()
        if self.config["scope_revision_authorized"] is not True:
            raise PermissionError("Confirmation scope revision requires approval")
        if self.config["sources_sha256"] != self.execution_sources(self.root):
            raise ValueError("Near-identity revision execution sources changed")
        binding = self.config["identity_review"]
        raw = Path(binding["path"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != binding["sha256"]:
            raise ValueError("Approved identity review changed")
        self.proposal = json.loads(raw)
        if (
            self.proposal["status"]
            != "passed_read_only_identity_metadata_review_pending_scope_approval"
            or self.proposal["inputs_sha256"][self.config["prior"]["manifest"]["path"]]
            != self.config["prior"]["manifest"]["sha256"]
        ):
            raise ValueError("Identity proposal belongs to a different prior cohort")
        self.rejected_paths = self.approved_mapping(manifest, self.proposal)
        if len(self.rejected_paths) != self.config["expected_replacements"]:
            raise ValueError("Approved replacement count differs from configuration")
        return manifest, report

    @staticmethod
    def execution_sources(root: Path) -> dict[str, str]:
        names = [
            "reproductions/unity_search_baseline/confirmation_near_revision.py",
            "reproductions/unity_search_baseline/confirmation_revision.py",
            "reproductions/unity_search_baseline/confirmation.py",
            "src/adaptive_astc/data/splitting.py",
            "src/adaptive_astc/utils/artifacts.py",
            "script/revise_unity_confirmation_near.py",
            "pyproject.toml",
            "uv.lock",
        ]
        return {name: A.sha256_file(root / name) for name in names}

    def inspect(self, row: JsonDict) -> JsonDict:
        inspected = super().inspect(row)
        if inspected["exclusion_reasons"]:
            raise ValueError("Frozen eligible cohort acquired an unapproved exclusion")
        if row["path"] in self.rejected_paths:
            inspected["exclusion_reasons"] = ["train_confirmation_near_identity"]
        return inspected

    def revise(self) -> JsonDict:
        result = super().revise()
        audit = A.read_json(Path(result["revision_audit"]))
        expected = [
            {
                "primary_index": row["primary_index_zero_based"],
                "old_path": row["original"]["path"],
                "new_path": row["replacement"]["path"],
                "original_reserve_index": row["reserve_position_one_based"] - 1,
            }
            for row in self.proposal["proposed_replacements"]
        ]
        if audit["replacements"] != expected:
            raise ValueError("Applied revision differs from approved slot mapping")
        result.update(
            scope="Approved train-confirmation near-identity revision, native re-audit pending",
            scope_revision_authorized=True,
            identity_review=self.config["identity_review"],
            replacements=audit["replacements"],
            model_forward_calls=0,
            actual_encoding_calls=0,
            sources_sha256=self.config["sources_sha256"],
        )
        A.write_json(self.report, result)
        return result

    @staticmethod
    def select_pixels(
        old: list[JsonDict], added: list[JsonDict], primary: list[JsonDict], proposal: JsonDict
    ) -> list[JsonDict]:
        """Preserve development rows and order confirmation rows by approved reservation."""
        def key(path: str) -> str:
            return path.replace("\\", "/").casefold()

        old_map = {key(row["path"]): row for row in old}
        added_map = {key(row["path"]): row for row in added}
        if len(old_map) != len(old) or len(added_map) != len(added):
            raise ValueError("Duplicate pixel identities")
        changes = proposal["proposed_replacements"]
        removed = {key(row["original"]["path"]) for row in changes}
        expected_added = {key(row["replacement"]["path"]) for row in changes}
        if (
            set(added_map) != expected_added
            or set(added_map) & set(old_map)
            or not removed <= set(old_map)
            or any(old_map[path]["source_split"] != "confirmation" for path in removed)
            or any(row["source_split"] != "confirmation" for row in added)
        ):
            raise ValueError("Pixel changes differ from approved confirmation replacements")
        old_confirmation = [row for row in old if row["source_split"] == "confirmation"]
        if len(old_confirmation) != len(primary):
            raise ValueError("Confirmation count changed")
        expected_order = [key(row["path"]) for row in old_confirmation]
        for row in changes:
            if key(old_confirmation[row["primary_index_zero_based"]]["path"]) != key(
                row["original"]["path"]
            ):
                raise ValueError("Original confirmation pixel order changed")
            expected_order[row["primary_index_zero_based"]] = key(row["replacement"]["path"])
        if [key(row["path"]) for row in primary] != expected_order:
            raise ValueError("Revised confirmation order changed outside approved slots")
        available = {path: row for path, row in old_map.items() if path not in removed}
        available.update(added_map)
        development = [row for row in old if row["source_split"] != "confirmation"]
        confirmation = [available[key(row["path"])] for row in primary]
        if {key(row["path"]) for row in development + confirmation} != set(available):
            raise ValueError("Unapproved pixel membership change")
        for source, pixel in zip(primary, confirmation, strict=True):
            if pixel["source_split"] != "confirmation" or (
                pixel["source_md4"] != source["fileHash"]
            ):
                raise ValueError("Revised confirmation source identity changed")
        return development + confirmation
