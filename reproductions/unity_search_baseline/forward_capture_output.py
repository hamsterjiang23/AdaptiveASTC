"""Audit measured forward-search traces and final capture outputs without candidate archives."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

import numpy as np
from PIL import Image

from adaptive_astc.config import JsonDict
from adaptive_astc.data.splitting import DatasetSplitter
from adaptive_astc.data.unity_capture_input import UnityCaptureInputAdapter
from adaptive_astc.evaluation.unity_quality import UnityQualityPrediction as Q
from adaptive_astc.evaluation.unity_quality import UnityTextureInput
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline.capture_output import UnityCaptureOutputAudit as O
from reproductions.unity_search_baseline.deployment import UnityDeploymentResult
from reproductions.unity_search_baseline.final_encoding import UnityFinalEncoding
from reproductions.unity_search_baseline.policy import UnitySearchDecision, UnitySearchPolicy
from reproductions.unity_search_baseline.quality import UnityQuality
from reproductions.unity_search_baseline.supplement import UnityASTCBackend
from reproductions.unity_search_baseline.system_variant_policy import (
    CandidateQueries,
    VariantOutcome,
    forward_search,
)


class RecordedForwardQueries(CandidateQueries):
    def outcome(self, selected: int, reason: str) -> VariantOutcome:
        return VariantOutcome(selected, tuple(self.indices), tuple(self.indices), reason)


class UnityForwardCaptureOutputAudit:
    @staticmethod
    def replay_choice(
        choice: JsonDict,
        predicted: UnitySearchDecision,
        policy: UnitySearchPolicy,
        texture: UnityTextureInput,
    ) -> VariantOutcome:
        records = choice["queries"]
        indices = [record["selected_index"] for record in records]
        if (
            choice["starting_decision"] != asdict(predicted)
            or not indices
            or indices
            != list(range(predicted.selected_index, predicted.selected_index + len(indices)))
            or indices[-1] >= 20
            or indices != choice["measured_indices"]
            or len(indices) != choice["candidates_measured"]
            or choice["selected_encoded_result_reused"] is not True
        ):
            raise ValueError("Measured forward trace differs from its predicted start or coverage")
        candidates = [{"metrics": {}} for _ in range(20)]
        strict = [False] * 20
        for record in records:
            index = record["selected_index"]
            candidates[index]["metrics"] = record["metrics"]
            strict[index] = Q.strict_quality(
                policy, texture, record["metrics"], predicted.effective_psnr_threshold
            )
            if record["strict_quality_met"] != strict[index]:
                raise ValueError("Query strict-quality flag differs from native metrics")
        replay = RecordedForwardQueries(
            {"decision": predicted, "candidates": candidates, "strict": strict},
            predicted.selected_index,
            None,
        )
        try:
            outcome = forward_search(replay)
        except KeyError as error:
            raise ValueError("Forward trace omitted a required actual measurement") from error
        if (
            list(outcome.measured_indices) != indices
            or outcome.selected_index != choice["selected_index"]
            or outcome.reason != choice["selection_reason"]
            or choice["strict_quality_met"] != strict[outcome.selected_index]
        ):
            raise ValueError("Final choice or stopping rule differs from the measured query trace")
        return outcome

    @staticmethod
    def signature(choice: JsonDict) -> str:
        return A.fingerprint(
            {
                key: [
                    {
                        name: value
                        for name, value in query.items()
                        if name not in {"timings", "trace_hash_seconds"}
                    }
                    for query in value
                ]
                if key == "queries"
                else value
                for key, value in choice.items()
            }
        )

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
        *,
        offset: int = 0,
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
            raise ValueError("Forward output and captured input coverage differ")
        predicted = result.predictions is not None
        expected_calls = (
            sum(choice["candidates_measured"] for choice in result.choices) if predicted else count
        )
        if result.timings["encoding_calls"] != expected_calls:
            raise ValueError("Actual encoding count differs from the measured trace")
        adapter.verify_references()
        output.mkdir(parents=True, exist_ok=False)
        rows: list[JsonDict] = []
        for index, (
            spec,
            texture,
            binding,
            policy,
            backend,
            quality,
            truth,
            choice,
            container,
        ) in enumerate(
            zip(
                adapter.textures,
                adapter.decision_inputs,
                adapter.bindings,
                policies,
                backends,
                qualities,
                selections,
                result.choices,
                result.containers,
                strict=True,
            )
        ):
            if (
                truth["asset"].replace("\\", "/").casefold()
                != binding["path"].replace("\\", "/").casefold()
            ):
                raise ValueError("Original selection belongs to another captured asset")
            selected = choice["selected_index"]
            if type(selected) is not int or not 0 <= selected < 20:
                raise ValueError("Invalid final candidate index")
            original_block, original_preset = truth["block_size"], truth["preset"]
            original_index = Q.GRID.index((int(original_block.split("x")[0]), original_preset))
            block, preset = Q.GRID[selected]
            header = backend.container(b"", texture.width, texture.height, block)
            payload_bytes = (
                ((texture.width + block - 1) // block)
                * ((texture.height + block - 1) // block)
                * 16
            )
            if len(container) != 16 + payload_bytes or container[:16] != header:
                raise ValueError("Final ASTC differs from the selected geometry")
            predicted_psnr = None
            if result.predictions is not None:
                predictions = result.predictions
                start = Q.select(
                    policy,
                    texture,
                    predictions["channel_mse"][index],
                    predictions["channel_zero"][index],
                    predictions["image_quality"][index],
                )
                cls.replay_choice(choice, start, policy, texture)
                if choice["source_index"] != offset + index:
                    raise ValueError("Forward source order differs from the complete input order")
                selected_record = next(
                    query for query in choice["queries"] if query["selected_index"] == selected
                )
                if hashlib.sha256(container).hexdigest() != selected_record["container_sha256"]:
                    raise ValueError("Final output differs from the selected measured ASTC")
                predicted_psnr = float(
                    Q.psnr(
                        predictions["channel_mse"][index],
                        predictions["channel_zero"][index],
                        texture,
                    )[selected]
                )
            elif selected != Q.GRID.index((8, "medium")):
                raise ValueError("Paired control must be fixed8/medium")
            with Image.open(spec.reference) as image:
                rgba = np.ascontiguousarray(np.asarray(image.convert("RGBA"))[::-1])
            if hashlib.sha256(rgba.tobytes()).hexdigest() != binding["callback_rgba_sha256"]:
                raise ValueError("Final quality input differs from callback pixels")
            decoded, decode_seconds = backend.decode_payload(
                container[16:], texture.width, texture.height, block, srgb=spec.srgb
            )
            metrics = quality.measure(
                rgba,
                decoded,
                need_alpha=spec.need_alpha,
                compute_ssim=spec.srgb and not spec.normal,
                normal=spec.normal,
                mip_count=spec.normal_metric_mips,
            )
            if predicted:
                UnityFinalEncoding.verify_metrics(metrics, selected_record["metrics"])
                if (
                    hashlib.sha256(decoded.tobytes()).hexdigest()
                    != selected_record["decoded_native_rgba_sha256"]
                ):
                    raise ValueError("Final decode differs from the measured selected pixels")
            if np.float32(metrics["black_pixel_ratio"]) != np.float32(texture.black_pixel_ratio):
                raise ValueError("Native metric black ratio differs from input pixels")
            threshold = O.threshold(policy, texture.black_pixel_ratio)
            strict = Q.strict_quality(policy, texture, metrics, threshold)
            astc, png = output / f"{index:05d}.astc", output / f"{index:05d}.png"
            astc.write_bytes(container)
            Image.fromarray(decoded[::-1]).save(png)
            original_side = Q.GRID[original_index][0]
            rows.append(
                {
                    "path": binding["path"],
                    "source_split": adapter.split,
                    "width": texture.width,
                    "height": texture.height,
                    "normal": spec.normal,
                    "srgb": spec.srgb,
                    "size_first": not spec.normal
                    and spec.srgb
                    and texture.width * texture.height
                    >= policy.table["sizeFirstMinSideLarge"] ** 2,
                    "selected_index": selected,
                    "block_size": f"{block}x{block}",
                    "preset": preset,
                    "original_selection": dict(truth),
                    "footprint_match": block == original_side,
                    "full_choice_match": selected == original_index,
                    "effective_psnr_threshold": threshold,
                    "strict_quality_met": strict,
                    "metrics": metrics,
                    "predicted_psnr": predicted_psnr,
                    "payload_bytes": payload_bytes,
                    "container_bytes": len(container),
                    "original_payload_bytes": ((texture.width + original_side - 1) // original_side)
                    * ((texture.height + original_side - 1) // original_side)
                    * 16,
                    "fixed8_payload_bytes": ((texture.width + 7) // 8)
                    * ((texture.height + 7) // 8)
                    * 16,
                    "quality_regression": truth["selection_reason"]
                    in {"first_valid", "size_first_strict"}
                    and not strict,
                    "larger_block": block > original_side,
                    "smaller_block": block < original_side,
                    "candidates_measured": choice["candidates_measured"] if predicted else 1,
                    "decode_audit_seconds": decode_seconds,
                    "astc_sha256": A.sha256_file(astc),
                    "decoded_png_sha256": A.sha256_file(png),
                }
            )
        if result.predictions is not None:
            np.savez_compressed(
                output / "predictions.npz",
                channel_mse=result.predictions["channel_mse"],
                channel_zero=result.predictions["channel_zero"],
                zero_probability=result.predictions["zero_probability"],
                image_quality=result.predictions["image_quality"],
            )
        A.write_json(output / "choices.json", {"rows": result.choices})
        A.write_json(output / "rows.json", {"rows": rows, "complete": True})
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
        summary = O.summarize(rows)
        counts = [row["candidates_measured"] for row in rows]
        groups: dict[str, list[JsonDict]] = defaultdict(list)
        parents: dict[str, list[bool]] = defaultdict(list)
        families: dict[str, list[bool]] = defaultdict(list)
        for row in rows:
            kind = "normal" if row["normal"] else "linear"
            if row["srgb"] and not row["normal"]:
                kind = "srgb_large" if row["size_first"] else "srgb_small"
            groups[kind].append(row)
            path = row["path"].replace("\\", "/")
            parents[path.rsplit("/", 1)[0].casefold()].append(row["footprint_match"])
            families[DatasetSplitter.asset_group(path).casefold()].append(row["footprint_match"])
        summary.update(
            rmse_scope=(
                "Stored model PSNR versus selected final output. "
                "Full20 candidate RMSE unavailable"
            ),
            actual_quality_pass_rate=summary["strict_quality_pass_rate"],
            quality_regression_images=sum(row["quality_regression"] for row in rows),
            larger_block_images=sum(row["larger_block"] for row in rows),
            smaller_block_images=sum(row["smaller_block"] for row in rows),
            payload_ratio_to_original=sum(row["payload_bytes"] for row in rows)
            / sum(row["original_payload_bytes"] for row in rows),
            payload_ratio_to_fixed8=sum(row["payload_bytes"] for row in rows)
            / sum(row["fixed8_payload_bytes"] for row in rows),
            candidates_measured={
                "mean": float(np.mean(counts)),
                "median": float(np.median(counts)),
                "p95": float(np.percentile(counts, 95)),
                "max": max(counts),
                "total": sum(counts),
            },
            groups={
                name: {
                    "images": len(items),
                    "accuracy": sum(item["footprint_match"] for item in items) / len(items),
                    "actual_quality_pass_rate": sum(item["strict_quality_met"] for item in items)
                    / len(items),
                }
                for name, items in groups.items()
            },
        )
        summary["groups"]["direct_parent_macro"] = {
            "groups": len(parents),
            "accuracy": float(np.mean([np.mean(items) for items in parents.values()])),
        }
        summary["groups"]["asset_family_macro"] = {
            "groups": len(families),
            "accuracy": float(np.mean([np.mean(items) for items in families.values()])),
        }
        return summary
