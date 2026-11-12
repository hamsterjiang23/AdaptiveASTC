"""Audit exact native pixel duplicates in frozen, completed capture archives."""

from __future__ import annotations

import hashlib
import io
import json
import time
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore as A


class UnityPixelIdentityAudit:
    """Read pixels only; never train, change splits, or infer model accuracy."""

    def __init__(self, config: Path) -> None:
        self.path = config.resolve()
        self.config_sha256 = A.sha256_file(self.path)
        self.config = A.read_json(self.path)
        self.inputs: dict[str, str] = {str(self.path): self.config_sha256}

    def bound_json(self, binding: JsonDict) -> JsonDict:
        path = Path(binding["path"]).resolve()
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != binding["sha256"]:
            raise ValueError(f"Frozen input changed: {path}")
        if str(path) in self.inputs and self.inputs[str(path)] != digest:
            raise ValueError("Conflicting frozen input bindings")
        self.inputs[str(path)] = digest
        # Parse exactly the bytes which were hashed, not a second read of a live file.
        return json.loads(raw.decode("utf-8-sig"))

    @staticmethod
    def pixel_identity(raw_png: bytes, width: int, height: int) -> JsonDict:
        with Image.open(io.BytesIO(raw_png)) as image:
            if image.size != (width, height):
                raise ValueError("Decoded native dimensions differ from receipt")
            rgba = image.convert("RGBA")
            rgb = rgba.convert("RGB")
            rgba_sha = hashlib.sha256(rgba.tobytes()).hexdigest()
            rgb_sha = hashlib.sha256(rgb.tobytes()).hexdigest()
            callback_sha = hashlib.sha256(
                rgba.transpose(Image.Transpose.FLIP_TOP_BOTTOM).tobytes()
            ).hexdigest()
            alpha_min, alpha_max = rgba.getchannel("A").getextrema()
            extrema = [band.getextrema() for band in rgba.split()]
            constant = all(bounds[0] == bounds[1] for bounds in extrema)
        return {
            "width": width,
            "height": height,
            "rgba_sha256": rgba_sha,
            "rgb_sha256": rgb_sha,
            "callback_rgba_sha256": callback_sha,
            "rgba_identity": A.fingerprint(["RGBA8", width, height, rgba_sha]),
            "rgb_identity": A.fingerprint(["RGB8", width, height, rgb_sha]),
            "constant_rgba": constant,
            "alpha_range": [alpha_min, alpha_max],
        }

    def batch_rows(self, batch: JsonDict) -> list[JsonDict]:
        split = batch["source_split"]
        if split not in {"train", "validation", "confirmation"}:
            raise ValueError("Only declared native development/confirmation splits are allowed")
        reference = self.bound_json(batch["reference_receipt"])
        options = self.bound_json(batch["options_receipt"])
        phase = self.bound_json(batch["phase_receipt"])
        if (
            reference["status"] != "passed"
            or options["status"] != "passed"
            or phase["status"] != "passed"
            or phase["process_exit_code"] != 0
            or phase["metadata_restore_conflicts"] != []
            or options["capture_receipt_sha256"] != batch["reference_receipt"]["sha256"]
        ):
            raise ValueError("Pixel audit requires complete, bound capture receipts")
        restoration = options["managed_source_restoration"]
        if (
            restoration["status"] != "restored"
            or restoration["original_sha256"] != restoration["restored_sha256"]
        ):
            raise ValueError("Capture managed source was not restored")
        archive = Path(batch["reference_receipt"]["path"]).resolve().parent
        manifest = self.bound_json(
            {"path": str(archive / "manifest.json"), "sha256": reference["manifest_sha256"]}
        )
        rows = reference["rows"]
        if (
            not rows
            or reference["images"] != len(rows)
            or options["images"] != len(rows)
            or len(options["rows"]) != len(rows)
            or manifest["reference_capture"] != rows
            or [row["path"] for row in manifest["splits"][split]] != [row["path"] for row in rows]
        ):
            raise ValueError("Archived reference membership is incomplete or inconsistent")
        result = []
        for index, (row, actual) in enumerate(zip(rows, options["rows"], strict=True)):
            if (
                row.get("source_split", "train") != split
                or row["path"] != actual["path"]
                or actual["index"] != index
                or (row["width"], row["height"]) != (actual["width"], actual["height"])
            ):
                raise ValueError("Native split, callback order or dimensions disagree")
            path = archive / f"{index:05d}" / "original.png"
            raw = path.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            if digest != row["artifacts_sha256"]["original.png"]:
                raise ValueError("Native PNG changed from capture receipt")
            pixels = self.pixel_identity(raw, row["width"], row["height"])
            if (
                pixels["callback_rgba_sha256"] != actual["rgba_sha256"]
                or pixels["rgb_sha256"] != row["reference_rgb_sha256"]
            ):
                raise ValueError("Decoded pixels disagree with native callback hashes")
            result.append(
                {
                    "path": row["path"],
                    "source_split": split,
                    "source_md4": row["source_md4"],
                    "run_id": batch["run_id"],
                    "reference": str(path),
                    "reference_sha256": digest,
                    **pixels,
                    "selected_block_size": row["selection"]["block_size"],
                    "selected_preset": row["selection"]["preset"],
                    "observed_options": {
                        key: actual[key]
                        for key in [
                            "need_alpha",
                            "profile",
                            "normal_pack",
                            "channel",
                            "srgb_importer",
                            "texture_type_importer",
                        ]
                    },
                }
            )
        return result

    @staticmethod
    def group_duplicates(rows: list[JsonDict], key: str) -> tuple[list[JsonDict], JsonDict]:
        by_identity: dict[str, list[int]] = defaultdict(list)
        for index, row in enumerate(rows):
            by_identity[row[key]].append(index)
        groups = []
        for identity, indices in sorted(by_identity.items()):
            if len(indices) < 2:
                continue
            members = [rows[index] for index in indices]
            counts = Counter(row["source_split"] for row in members)
            groups.append(
                {
                    "identity": identity,
                    "row_indices": indices,
                    "split_counts": dict(counts),
                    "cross_split": len(counts) > 1,
                    "rgba_variants": len({row["rgba_identity"] for row in members}),
                    "observed_option_variants": len(
                        {A.fingerprint(row["observed_options"]) for row in members}
                    ),
                    "selected_choices": sorted(
                        {f"{r['selected_block_size']}/{r['selected_preset']}" for r in members}
                    ),
                }
            )
        cross = [group for group in groups if group["cross_split"]]
        return groups, {
            "unique_identities": len(by_identity),
            "duplicate_groups": len(groups),
            "images_in_duplicate_groups": sum(len(group["row_indices"]) for group in groups),
            "redundant_images": sum(len(group["row_indices"]) - 1 for group in groups),
            "cross_split_groups": len(cross),
            "cross_split_images": dict(
                Counter(rows[i]["source_split"] for group in cross for i in group["row_indices"])
            ),
            "groups_with_different_rgba": sum(group["rgba_variants"] > 1 for group in groups),
            "groups_with_different_choices": sum(len(g["selected_choices"]) > 1 for g in groups),
        }

    def run(self) -> JsonDict:
        started = time.perf_counter()
        report = Path(self.config["report"]).resolve()
        output = Path(self.config["output"]).resolve()
        if report.is_relative_to(output):
            raise ValueError("Public report must be outside the raw audit output")
        if output.exists() or report.exists():
            raise FileExistsError("Use a fresh pixel audit output and report")
        if not self.config["batches"]:
            raise ValueError("At least one completed capture batch is required")
        output.mkdir(parents=True, exist_ok=False)
        state: JsonDict = {
            "status": "running",
            "config_sha256": self.config_sha256,
            "source_sha256": A.sha256_file(Path(__file__)),
            "coverage": "explicit_completed_archives_only",
            "test_opened": False,
            "training_updates": 0,
            "splits_modified": False,
            "independent_test_isolation_proven": False,
            "scope": "Exact dimensions + RGBA8; RGB-only diagnostic; near duplicates not audited",
        }
        report.parent.mkdir(parents=True, exist_ok=True)
        # Claim the public identity before entering cleanup that may rewrite it.
        with report.open("x", encoding="utf-8") as stream:
            json.dump(state, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        try:
            rows = []
            for batch in self.config["batches"]:
                rows.extend(self.batch_rows(batch))
            assets = [row["path"].replace("\\", "/").casefold() for row in rows]
            if len(assets) != len(set(assets)):
                raise ValueError("An asset path appears more than once in audited captures")
            counts = dict(Counter(row["source_split"] for row in rows))
            if counts != self.config["expected_counts"]:
                raise ValueError("Audited counts differ from frozen expected coverage")
            rgba_groups, rgba_summary = self.group_duplicates(rows, "rgba_identity")
            rgb_groups, rgb_summary = self.group_duplicates(rows, "rgb_identity")
            for path, digest in self.inputs.items():
                if A.sha256_file(Path(path)) != digest:
                    raise ValueError("Frozen audit inputs changed during execution")
            details = output / "pixel-identities.json"
            A.write_json(
                details, {"rows": rows, "rgba_groups": rgba_groups, "rgb_groups": rgb_groups}
            )
            state.update(
                status="passed",
                counts=counts,
                rgba=rgba_summary,
                rgb_only=rgb_summary,
                constant_rgba_images=sum(row["constant_rgba"] for row in rows),
                details=str(details),
                details_sha256=A.sha256_file(details),
                inputs_sha256=self.inputs,
            )
        except BaseException as error:
            state.update(status="failed", error=repr(error))
            raise
        finally:
            state["wall_seconds"] = time.perf_counter() - started
            A.write_json(report, state)
        return state
