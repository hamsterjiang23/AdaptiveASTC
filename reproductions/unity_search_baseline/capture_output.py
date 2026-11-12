"""Measure final native outputs using captured inputs, without supplemental candidates."""

from __future__ import annotations

import hashlib
from dataclasses import asdict
from pathlib import Path

import numpy as np
from PIL import Image

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_capture_input import UnityCaptureInputAdapter
from adaptive_astc.evaluation.unity_quality import UnityQualityPrediction as Q
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline.deployment import UnityDeploymentResult
from reproductions.unity_search_baseline.policy import UnitySearchPolicy
from reproductions.unity_search_baseline.quality import UnityQuality
from reproductions.unity_search_baseline.supplement import UnityASTCBackend


class UnityCaptureOutputAudit:
    """The caller audits provenance and seals inference; this class only scores its outputs."""

    @staticmethod
    def threshold(policy: UnitySearchPolicy, black_ratio: float) -> float:
        black = float(np.float32(black_ratio))
        table = policy.table
        if black > table["blackPixelRatioStrong"]:
            return table["blackElevatedPsnrStrongDb"]
        if black > table["blackPixelRatioMild"]:
            return table["blackElevatedPsnrMildDb"]
        return table["targetPsnrDb"]

    @classmethod
    def run(
        cls,
        adapter: UnityCaptureInputAdapter,
        policies: list[UnitySearchPolicy],
        backends: list[UnityASTCBackend],
        qualities: list[UnityQuality],
        selections: list[JsonDict],
        result: UnityDeploymentResult,
        output: Path,
    ) -> JsonDict:
        count = len(adapter.textures)
        if any(
            len(values) != count
            for values in [
                policies,
                backends,
                qualities,
                selections,
                result.choices,
                result.containers,
            ]
        ):
            raise ValueError("Final output and captured input coverage differ")
        if result.timings["encoding_calls"] != count or result.timings["images"] != count:
            raise ValueError("Require exactly one final encoding per image in each trial")
        adapter.verify_references()
        output.mkdir(parents=True, exist_ok=False)
        rows: list[JsonDict] = []
        for i, spec in enumerate(adapter.textures):
            choice, truth = result.choices[i], selections[i]
            texture, binding, policy = adapter.decision_inputs[i], adapter.bindings[i], policies[i]
            if (
                truth["asset"].replace("\\", "/").casefold()
                != binding["path"].replace("\\", "/").casefold()
            ):
                raise ValueError("Original selection belongs to a different captured asset")
            index = choice["selected_index"]
            if type(index) is not int or not 0 <= index < len(Q.GRID):
                raise ValueError("Invalid final candidate index")
            block, preset = Q.GRID[index]
            original = (truth["block_size"], truth["preset"])
            if original not in {(f"{b}x{b}", p) for b, p in Q.GRID}:
                raise ValueError("Original capture selection is outside the native candidate grid")
            container = result.containers[i]
            size = ((texture.width + block - 1) // block) * ((texture.height + block - 1) // block)
            if len(container) != 16 + size * 16 or container[:16] != backends[i].container(
                b"", texture.width, texture.height, block
            ):
                raise ValueError("Final ASTC header or payload differs from the selected geometry")
            with Image.open(spec.reference) as image:
                rgba = np.ascontiguousarray(np.asarray(image.convert("RGBA"))[::-1])
            if hashlib.sha256(rgba.tobytes()).hexdigest() != binding["callback_rgba_sha256"]:
                raise ValueError("Final quality input differs from original callback pixels")
            decoded, decode_seconds = backends[i].decode_payload(
                container[16:], texture.width, texture.height, block, srgb=spec.srgb
            )
            metrics = qualities[i].measure(
                rgba,
                decoded,
                need_alpha=spec.need_alpha,
                compute_ssim=spec.srgb and not spec.normal,
                normal=spec.normal,
                mip_count=spec.normal_metric_mips,
            )
            if np.float32(metrics["black_pixel_ratio"]) != np.float32(texture.black_pixel_ratio):
                raise ValueError("Native metric black ratio differs from the input policy")
            threshold = cls.threshold(policy, texture.black_pixel_ratio)
            predicted_psnr = None
            if result.predictions is not None:
                predictions = result.predictions
                expected = Q.select(
                    policy,
                    texture,
                    predictions["channel_mse"][i],
                    predictions["channel_zero"][i],
                    predictions["image_quality"][i],
                )
                if choice != asdict(expected):
                    raise ValueError("Final choice differs from the sealed model predictions")
                predicted_psnr = float(
                    Q.psnr(predictions["channel_mse"][i], predictions["channel_zero"][i], texture)[
                        index
                    ]
                )
            astc, png = output / f"{i:05d}.astc", output / f"{i:05d}.png"
            astc.write_bytes(container)
            Image.fromarray(decoded[::-1]).save(png)
            rows.append(
                {
                    "path": binding["path"],
                    "source_split": adapter.split,
                    "width": texture.width,
                    "height": texture.height,
                    "normal": spec.normal,
                    "srgb": spec.srgb,
                    "selected_index": index,
                    "block_size": f"{block}x{block}",
                    "preset": preset,
                    "original_selection": dict(truth),
                    "footprint_match": original[0] == f"{block}x{block}",
                    "full_choice_match": original == (f"{block}x{block}", preset),
                    "effective_psnr_threshold": threshold,
                    "strict_quality_met": Q.strict_quality(policy, texture, metrics, threshold),
                    "metrics": metrics,
                    "predicted_psnr": predicted_psnr,
                    "payload_bytes": len(container) - 16,
                    "container_bytes": len(container),
                    "decode_seconds": decode_seconds,
                    "astc_sha256": A.sha256_file(astc),
                    "decoded_png_sha256": A.sha256_file(png),
                }
            )
            A.write_json(output / "rows.json", {"rows": rows, "complete": len(rows) == count})
        if result.predictions is not None:
            np.savez_compressed(
                output / "predictions.npz",
                channel_mse=result.predictions["channel_mse"],
                channel_zero=result.predictions["channel_zero"],
                zero_probability=result.predictions["zero_probability"],
                image_quality=result.predictions["image_quality"],
            )
        A.write_json(output / "choices.json", {"rows": result.choices})
        adapter.verify_references()
        return {
            "rows": rows,
            "summary": cls.summarize(rows),
            "outputs_sha256": {
                path.name: A.sha256_file(path) for path in output.iterdir() if path.is_file()
            },
        }

    @staticmethod
    def summarize(rows: list[JsonDict]) -> JsonDict:
        if not rows:
            raise ValueError("Cannot summarize an empty native evaluation")
        classes = ["6x6", "8x8", "10x10", "12x12"]
        confusion = np.zeros((4, 4), dtype=np.int64)
        for row in rows:
            confusion[
                classes.index(row["original_selection"]["block_size"]),
                classes.index(row["block_size"]),
            ] += 1
        per_class = {}
        for i, name in enumerate(classes):
            support, predicted = int(confusion[i].sum()), int(confusion[:, i].sum())
            per_class[name] = {
                "support": support,
                "predicted": predicted,
                "recall": float(confusion[i, i] / support) if support else None,
                "precision": float(confusion[i, i] / predicted) if predicted else None,
            }
        errors = [
            (row["predicted_psnr"] - row["metrics"]["psnr"]) ** 2
            for row in rows
            if row["predicted_psnr"] is not None
            and not row["normal"]
            and abs(row["metrics"]["psnr"] - row["effective_psnr_threshold"]) <= 3
        ]
        return {
            "images": len(rows),
            "classes": classes,
            "confusion": confusion.tolist(),
            "per_class": per_class,
            "footprint_accuracy": sum(row["footprint_match"] for row in rows) / len(rows),
            "full_choice_accuracy": sum(row["full_choice_match"] for row in rows) / len(rows),
            "balanced_accuracy": float(
                np.mean([entry["recall"] for entry in per_class.values() if entry["support"]])
            ),
            "strict_quality_pass_rate": sum(row["strict_quality_met"] for row in rows) / len(rows),
            "quality_violation_count": sum(not row["strict_quality_met"] for row in rows),
            "payload_bytes": sum(row["payload_bytes"] for row in rows),
            "container_bytes": sum(row["container_bytes"] for row in rows),
            "selected_color_near_threshold_count": len(errors),
            "selected_color_near_threshold_rmse_db": float(np.sqrt(np.mean(errors)))
            if errors
            else None,
            "all_candidate_rmse_db": None,
            "rmse_scope": "Only the selected candidate was encoded; no unselected quality targets",
        }
