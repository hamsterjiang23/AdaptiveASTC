"""Source validation, image decoding, and immutable RGB view caching."""

from pathlib import Path
from typing import cast

import imagehash
import numpy as np
from Crypto.Hash import MD4
from PIL import Image

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore


class ImagePreprocessor:
    """Verify source MD4 and cache the fixed RGB224 input representation."""

    def __init__(self, image_root: Path, cache_root: Path) -> None:
        self.image_root = image_root
        self.cache_root = cache_root

    def decode(self, row: JsonDict) -> tuple[JsonDict, np.ndarray]:
        source = self.image_root / str(row["path"])
        digest = MD4.new()
        with source.open("rb") as stream:
            header = stream.read(32)
            if header.startswith(b"\x89PNG\r\n\x1a\n"):
                if len(header) < 25:
                    raise ValueError("truncated_png_header")
                if header[24] > 8:
                    raise ValueError("unsupported_png_bit_depth")
            stream.seek(0)
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest().lower() != str(row["fileHash"]).lower():
            raise ValueError("md4_mismatch")
        with Image.open(source) as image:
            if getattr(image, "n_frames", 1) != 1:
                raise ValueError("multiframe")
            if image.format == "TIFF":
                bits = getattr(image, "tag_v2", {}).get(258, (8,))
                samples = (bits,) if isinstance(bits, int) else bits
                if any(value > 8 for value in samples):
                    raise ValueError("unsupported_tiff_bit_depth")
            if image.mode not in {"1", "L", "LA", "P", "RGB", "RGBA", "CMYK"}:
                raise ValueError("unsupported_pixel_mode")
            image.load()
            has_alpha = "A" in image.getbands() or "transparency" in image.info
            alpha_nonopaque = False
            if has_alpha:
                alpha_range = cast(
                    tuple[int, int], image.convert("RGBA").getchannel("A").getextrema()
                )
                alpha_nonopaque = alpha_range[0] < 255
            rgb = image.convert("RGB")
            preview = np.asarray(rgb.resize((32, 32), Image.Resampling.BILINEAR), dtype=np.uint8)
            phash = int(str(imagehash.phash(rgb, hash_size=8)), 16)
            pixels = np.asarray(rgb.resize((224, 224), Image.Resampling.BILINEAR), dtype=np.uint8)
            width, height = image.size
        relative_cache = Path("cache") / str(row["fileHash"])[:2] / f"{row['fileHash']}.npy"
        target = self.cache_root / relative_cache
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        with temporary.open("wb") as stream:
            np.save(stream, pixels, allow_pickle=False)
        if target.exists():
            if ArtifactStore.sha256_file(target) != ArtifactStore.sha256_file(temporary):
                raise RuntimeError("Existing image cache differs; prepare a new run directory")
            temporary.unlink()
        else:
            temporary.replace(target)
        result = dict(row)
        result.update(
            {
                "width": width,
                "height": height,
                "has_alpha": has_alpha,
                "alpha_nonopaque": alpha_nonopaque,
                "phash": phash,
                "cache": relative_cache.as_posix(),
                "cache_sha256": ArtifactStore.sha256_file(target),
            }
        )
        result.pop("alternatives", None)
        return result, preview
