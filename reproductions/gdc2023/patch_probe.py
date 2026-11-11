"""Check cropped-block equivalence and transform sensitivity with the frozen encoder."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
from PIL import Image

from adaptive_astc.config import CLASSES, JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore
from reproductions.common.encoder import ASTCEncoder


class GDCPatchProbe:
    def __init__(self, corpus: Path, executable: Path, output: Path, report: Path) -> None:
        self.corpus, self.executable = corpus.resolve(), executable.resolve()
        self.output, self.report = output.resolve(), report.resolve()

    def run(self, image_count: int = 20) -> JsonDict:
        if image_count < 1:
            raise ValueError("Positive probe image count required")
        if self.output.exists() and any(self.output.iterdir()):
            raise FileExistsError("Probe output must be new")
        document = ArtifactStore.read_json(self.corpus / "corpus.json")
        measured = Path(document["config"]["measured_root"])
        protocol = ArtifactStore.read_json(measured / "protocol.json")
        if ArtifactStore.sha256_file(self.executable) != protocol["encoder_sha256"]:
            raise ValueError("Probe encoder differs from frozen candidate encoder")
        rows = sorted(document["splits"]["train"], key=lambda row: row["pixel_count"])
        selected = [
            rows[int(i)]
            for i in np.linspace(0, len(rows) - 1, min(image_count, len(rows)), dtype=int)
        ]
        encoder = ASTCEncoder(self.executable, threads=1)
        started = time.perf_counter()
        results: list[JsonDict] = []
        for row in selected:
            folder = self.output / f"{row['index']:05d}"
            folder.mkdir(parents=True)
            reference_path = Path(row["reference"])
            if ArtifactStore.sha256_file(reference_path) != row["reference_sha256"]:
                raise ValueError("Probe reference changed")
            x = 120 if row["width"] >= 360 else 0
            y = 120 if row["height"] >= 360 else 0
            width, height = min(240, row["width"] - x), min(240, row["height"] - y)
            with Image.open(reference_path) as image:
                patch = image.convert("RGB").crop((x, y, x + width, y + height))
            arrays = {
                "original": np.asarray(patch),
                "horizontal": np.asarray(patch)[:, ::-1],
                "vertical": np.asarray(patch)[::-1],
                "rotate90": np.rot90(np.asarray(patch)),
            }
            for transform, pixels in arrays.items():
                Image.fromarray(pixels).save(folder / f"{transform}.png")
            receipt = ArtifactStore.read_json(reference_path.parent / "receipt.json")
            for name in CLASSES:
                full_decode_path = reference_path.parent / f"{name}.png"
                if (
                    ArtifactStore.sha256_file(full_decode_path)
                    != receipt["artifacts_sha256"][f"{name}.png"]
                ):
                    raise ValueError("Probe full decode changed")
                with Image.open(full_decode_path) as image:
                    expected = np.asarray(image.convert("RGB").crop((x, y, x + width, y + height)))
                block = int(name.split("x")[0])
                base_mse = float(np.square(arrays["original"].astype(float) - expected).mean())
                for transform, pixels in arrays.items():
                    output = folder / f"{name}-{transform}.astc"
                    _, seconds, log = encoder.encode(
                        folder / f"{transform}.png", output, (block, block), "medium"
                    )
                    (folder / f"{name}-{transform}.txt").write_text(log, encoding="utf-8")
                    decoded_path = output.with_suffix(".png")
                    encoder.decode(output, decoded_path)
                    with Image.open(decoded_path) as image:
                        decoded = np.asarray(image.convert("RGB"))
                    mse = float(np.square(pixels.astype(float) - decoded).mean())
                    delta_db = 10 * np.log10(base_mse / mse) if base_mse > 0 and mse > 0 else None
                    results.append(
                        {
                            "index": row["index"],
                            "path": row["path"],
                            "footprint": name,
                            "transform": transform,
                            "box": [x, y, width, height],
                            "image_dimensions": [row["width"], row["height"]],
                            "decode_equals_full_region": bool(np.array_equal(decoded, expected))
                            if transform == "original"
                            else None,
                            "full_region_mse_byte": base_mse,
                            "standalone_mse_byte": mse,
                            "psnr_delta_db": float(delta_db) if delta_db is not None else None,
                            "encode_seconds": seconds,
                            "astc_sha256": ArtifactStore.sha256_file(output),
                        }
                    )
            ArtifactStore.write_json(
                self.output / "progress.json",
                {"candidate_transforms": len(results), "seconds": time.perf_counter() - started},
            )
        original = [row for row in results if row["transform"] == "original"]
        result = {
            "status": "measured",
            "images": len(selected),
            "candidate_transforms": len(results),
            "encoder_sha256": protocol["encoder_sha256"],
            "corpus_fingerprint": document["fingerprint"],
            "independent_patch_matches": sum(row["decode_equals_full_region"] for row in original),
            "independent_patch_comparisons": len(original),
            "rows": results,
            "wall_seconds": time.perf_counter() - started,
            "scope": "source RGB GDC astcenc3.3 medium; sampled training images; no test",
            "augmentations_enabled": False,
        }
        ArtifactStore.write_json(self.report, result)
        return result
