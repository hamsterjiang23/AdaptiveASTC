"""Install reversible timing-only edits in the selected Unity source checkout."""

from __future__ import annotations

import difflib
import hashlib
import json
from pathlib import Path


class EngineTimingPatch:
    """Refuse ambiguous replacements and preserve originals before writing."""

    def __init__(self, engine: Path, backup_dir: Path) -> None:
        self.engine = engine.resolve()
        self.backup_dir = backup_dir.resolve()

    def apply(self) -> dict[str, str]:
        folder = Path("Editor/Src/AssetPipeline/TextureImporting")
        replacements = {
            "ASTCCompressor.cpp": [
                (
                    '#include "ASTCCompressor.h"',
                    '#include "ASTCCompressor.h"\n#include "ASTCBenchmark.h"',
                ),
                (
                    "                    *outBestParam = cachedParam;",
                    "                    ASTCBenchmark::CacheHit();\n"
                    "                    *outBestParam = cachedParam;",
                ),
                (
                    "        TestAllParameterCombinations(originalRef,",
                    "        ASTCBenchmark::SearchStart();\n"
                    "        TestAllParameterCombinations(originalRef,",
                ),
                (
                    "        // Step 6: Save results to cache for future use",
                    "        ASTCBenchmark::SearchEnd();\n"
                    "\n"
                    "        // Step 6: Save results to cache for future use",
                ),
                (
                    "            // Calculate quality metrics",
                    "            ASTCBenchmark::Measured();\n"
                    "            // Calculate quality metrics",
                ),
                (
                    "\n            int astcProfile = GetAstcEncProfile(textureFormat, useSRGB);",
                    "\n"
                    "            ASTCBenchmark::Candidate();\n"
                    "            int astcProfile = GetAstcEncProfile(textureFormat, useSRGB);",
                ),
                (
                    "    if (!g_useOptimization)\n        return false;",
                    "    ASTCBenchmark::FormatScope astcFormatTiming;\n"
                    "    if (!g_useOptimization)\n"
                    "        return false;",
                ),
                (
                    "    *outOptimalFormat = optimalFormat;",
                    "    ASTCBenchmark::Selected(bestParam->blockSize, bestParam->qualityLevel);\n"
                    "    *outOptimalFormat = optimalFormat;",
                ),
                (
                    "                    // Directly use compressed data from memory",
                    "                    ASTCBenchmark::Reused();\n"
                    "                    // Directly use compressed data from memory",
                ),
                (
                    "                            selectedBySizeFirst = true;",
                    '                            ASTCBenchmark::Reason("size_first_strict");\n'
                    "                            selectedBySizeFirst = true;",
                ),
                (
                    "                if (isBetter)\n                {",
                    "                if (isBetter)\n                {\n"
                    '                    ASTCBenchmark::Reason("first_valid");',
                ),
                (
                    "            sharedResult.bestResult = sizeFirstFallbackResult;",
                    '            ASTCBenchmark::Reason("size_first_relaxed");\n'
                    "            sharedResult.bestResult = sizeFirstFallbackResult;",
                ),
                (
                    "            *outBestParam = finalSelectedResult.param;",
                    '            ASTCBenchmark::Reason("highest_psnr_fallback");\n'
                    "            *outBestParam = finalSelectedResult.param;",
                ),
            ],
            "ImageOperations.cpp": [
                (
                    '#include "ASTCCompressor.h"',
                    '#include "ASTCCompressor.h"\n#include "ASTCBenchmark.h"',
                ),
                (
                    "    SharedTextureData* srcData = tex.AcquireSharedTextureData();",
                    "    const char* astcBenchmarkPath = "
                    "IsCompressedASTCTextureFormat(compressedFormat) ? assetPath : NULL;\n"
                    "    ASTCBenchmark::PipelineScope astcPipelineTiming(astcBenchmarkPath);\n"
                    "    SharedTextureData* srcData = tex.AcquireSharedTextureData();",
                ),
            ],
        }
        prepared: list[tuple[Path, bytes, bytes]] = []
        hashes: dict[str, str] = {}
        for name, edits in replacements.items():
            target = self.engine / folder / name
            original = target.read_bytes()
            if b'"ASTCBenchmark.h"' in original:
                raise ValueError(f"Timing patch already present: {target}")
            text = original.decode("utf-8").replace("\r\n", "\n")
            for before, after in edits:
                if text.count(before) != 1:
                    raise ValueError(f"Expected one patch anchor in {name}: {before!r}")
                text = text.replace(before, after, 1)
            newline = "\r\n" if b"\r\n" in original else "\n"
            modified = text.replace("\n", newline).encode("utf-8")
            hashes[name] = hashlib.sha256(original).hexdigest()
            prepared.append((target, original, modified))
        self.backup_dir.mkdir(parents=True, exist_ok=False)
        patches: list[str] = []
        for target, original, modified in prepared:
            (self.backup_dir / target.name).write_bytes(original)
            target.write_bytes(modified)
            patches.extend(
                difflib.unified_diff(
                    original.decode().splitlines(True),
                    modified.decode().splitlines(True),
                    fromfile=target.name,
                    tofile=target.name,
                )
            )
        header = Path(__file__).with_name("ASTCBenchmark.h")
        (self.engine / folder / header.name).write_bytes(header.read_bytes())
        (self.backup_dir / "timing.patch").write_text("".join(patches), encoding="utf-8")
        (self.backup_dir / "original_hashes.json").write_text(
            json.dumps(hashes, indent=2), encoding="utf-8"
        )
        return hashes
