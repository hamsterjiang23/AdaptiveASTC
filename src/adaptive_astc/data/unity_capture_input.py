"""Build native inference inputs from capture pixels and importer/callback properties."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

import numpy as np
from PIL import Image

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_inference import UnityInferenceInput, UnityInferenceTexture
from adaptive_astc.evaluation.unity_quality import UnityTextureInput
from adaptive_astc.utils.artifacts import ArtifactStore as A


class UnityCaptureInputAdapter:
    """Project already-audited capture rows to input-only records, preserving the split.

    The caller must verify capture provenance and seal a model before held-out forward passes.
    This adapter neither opens an evaluation nor reads labels, candidates or target arrays.
    """

    def __init__(self, rows: list[JsonDict], split: str) -> None:
        if split not in {"train", "validation", "confirmation"} or not rows:
            raise ValueError("Require a nonempty declared native capture split")
        self.split = split
        self.textures: list[UnityInferenceTexture] = []
        self.decision_inputs: list[UnityTextureInput] = []
        self.bindings: list[JsonDict] = []
        seen: set[str] = set()
        for row in rows:
            asset = row["path"].replace("\\", "/").casefold()
            if row["source_split"] != split or asset in seen:
                raise ValueError("Capture input split or asset uniqueness changed")
            seen.add(asset)
            texture, decision, binding = self.project(row)
            self.textures.append(texture)
            self.decision_inputs.append(decision)
            self.bindings.append(binding)
        self.fingerprint = A.fingerprint({"split": split, "inputs": self.bindings})

    @staticmethod
    def project(row: JsonDict) -> tuple[UnityInferenceTexture, UnityTextureInput, JsonDict]:
        """Read only the capture fields which exist before candidate measurement."""
        actual, imported = row["actual_options"], row["import_metadata"]
        width, height = row["width"], row["height"]
        if any(type(value) is not int or value < 1 for value in [width, height]):
            raise ValueError("Capture dimensions must be positive integers")
        asset = row["path"].replace("\\", "/").casefold()
        if any(
            name.replace("\\", "/").casefold() != asset
            for name in [actual["path"], imported["asset"]]
        ):
            raise ValueError("Callback/import asset differs from the reference")
        if (
            imported["success"] is not True
            or imported["texture_dimension"] != "Tex2D"
            or imported["texture_type"] not in {"Default", "Sprite", "NormalMap"}
            or any(
                type(value) is not bool
                for value in [
                    imported["srgb"],
                    imported["mipmaps"],
                    actual["need_alpha"],
                    actual["srgb_importer"],
                    actual["normal_pack"],
                ]
            )
            or type(actual["profile"]) is not int
            or actual["profile"] not in {0, 1}
            or type(actual["channel"]) is not int
            or actual["channel"] != 4
            or actual["normal_pack"]
            or actual["texture_type_importer"] != imported["texture_type"]
            or actual["srgb_importer"] != imported["srgb"]
            or (actual["profile"] == 0) != imported["srgb"]
        ):
            raise ValueError("Capture input requires matching LDR Tex2D RGBA properties")
        for source in [actual, imported]:
            if any(type(source[key]) is not int for key in ["width", "height"]) or (
                source["width"],
                source["height"],
            ) != (width, height):
                raise ValueError("Callback/import dimensions differ from the reference")
        normal = imported["texture_type"] == "NormalMap"
        mips = min(4, max(width, height).bit_length()) if normal and imported["mipmaps"] else 1
        path = Path(row["reference_png"]).resolve()
        texture = UnityInferenceTexture(path, imported["srgb"], normal, actual["need_alpha"], mips)
        texture.validate()
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != row["reference_sha256"]:
            raise ValueError("Native reference PNG changed")
        with Image.open(io.BytesIO(raw)) as image:
            if image.size != (width, height):
                raise ValueError("Native reference PNG dimensions changed")
            pixels = np.asarray(image.convert("RGBA"), dtype=np.uint8)
        callback_sha = hashlib.sha256(np.ascontiguousarray(pixels[::-1]).tobytes()).hexdigest()
        if callback_sha != actual["rgba_sha256"]:
            raise ValueError("Native RGBA bytes differ from the encoder callback")
        alpha_constant = bool(pixels[:, :, 3].min() == pixels[:, :, 3].max())
        black = float(np.mean(np.all(pixels[:, :, :3] == 0, axis=2)))
        decision = UnityTextureInput(
            width,
            height,
            texture.srgb,
            normal,
            texture.need_alpha,
            alpha_constant,
            black,
        )
        binding = {
            "path": row["path"],
            "source_split": row["source_split"],
            "reference_png": str(path),
            "reference_sha256": row["reference_sha256"],
            "width": width,
            "height": height,
            "callback_rgba_sha256": callback_sha,
            "srgb": texture.srgb,
            "texture_type": imported["texture_type"],
            "normal": normal,
            "need_alpha": texture.need_alpha,
            "normal_metric_mips": mips,
            "alpha_constant": alpha_constant,
            "black_pixel_ratio": black,
        }
        return texture, decision, binding

    def verify_references(self) -> None:
        for row in self.bindings:
            if A.sha256_file(Path(row["reference_png"])) != row["reference_sha256"]:
                raise ValueError("Bound native input changed")

    def dataset(self) -> UnityInferenceInput:
        self.verify_references()
        return UnityInferenceInput(self.textures, patch_size=240)
