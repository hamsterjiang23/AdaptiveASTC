from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore
from reproductions.unity_search_baseline.benchmark import UnitySearchBaseline
from reproductions.unity_search_baseline.metadata import ManagedCaptureHook, UnityOptionCapture

SOURCE = """class Callback {
    unsafe static void HandleOptimizeCompress(byte* srcdata, int width, int height, int channel,
        TextureFormat format, bool needAlpha, byte* compressedTextureBuffer, int astc3rd_quality,
        bool astc3rd_packnormal, int astcenc_profile, bool bSaveASTC, string outputASTCfilename,
        bool rdoEnabled, float rdoQualityScalar, int rdoLookback)
    {
        OriginalEncoder(srcdata);
    }
}
"""


@pytest.mark.parametrize("bom,newline", [(False, "\n"), (True, "\r\n")])
def test_hook_preserves_original_callback_and_encoding(bom: bool, newline: str) -> None:
    original = (b"\xef\xbb\xbf" if bom else b"") + SOURCE.replace("\n", newline).encode()
    patched = ManagedCaptureHook.instrument(original)
    assert patched.startswith(b"\xef\xbb\xbf") == bom
    assert patched.count(b"OriginalEncoder(srcdata);") == 1
    assert patched.count(b"RecordASTCTrainingOptions(") == 2
    assert patched.index(b"RecordASTCTrainingOptions(srcdata") < patched.index(
        b"OriginalEncoder(srcdata);"
    )
    if newline == "\r\n":
        assert b"\n" not in patched.replace(b"\r\n", b"")
    with pytest.raises(ValueError, match="already patched"):
        ManagedCaptureHook.instrument(patched)


def test_restore_exact_bytes_and_reject_independent_edit(tmp_path: Path) -> None:
    source = tmp_path / "source.cs"
    original = SOURCE.encode()
    source.write_bytes(original)
    hook = ManagedCaptureHook(tmp_path / "journal")
    installed = hook.install(source)
    assert installed["status"] == "installed"
    assert ArtifactStore.sha256_file(source) == installed["instrumented_sha256"]
    patched = source.read_bytes()
    source.write_bytes(patched + b"// independent change")
    with pytest.raises(ValueError, match="independently"):
        hook.restore()
    assert source.read_bytes().endswith(b"// independent change")
    source.write_bytes(patched)
    restored = hook.restore()
    assert source.read_bytes() == original
    assert restored["restored_sha256"] == installed["original_sha256"]
    assert hook.restore() == restored


def test_prepared_journal_recovers_after_install_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.cs"
    source.write_bytes(SOURCE.encode())
    hook = ManagedCaptureHook(tmp_path / "journal")
    original_replace = ManagedCaptureHook.replace_bytes

    def replace_then_fail(path: Path, payload: bytes) -> None:
        original_replace(path, payload)
        if path == source:
            raise OSError("simulated interruption after replacement")

    monkeypatch.setattr(ManagedCaptureHook, "replace_bytes", staticmethod(replace_then_fail))
    with pytest.raises(OSError, match="interruption"):
        hook.install(source)
    assert ArtifactStore.read_json(hook.folder / "receipt.json")["status"] == "prepared"
    monkeypatch.setattr(ManagedCaptureHook, "replace_bytes", staticmethod(original_replace))
    hook.restore()
    assert source.read_bytes() == SOURCE.encode()


def metadata_fixture(tmp_path: Path) -> tuple[UnitySearchBaseline, JsonDict, JsonDict]:
    baseline = UnitySearchBaseline(tmp_path, tmp_path / "project", tmp_path / "exe", tmp_path)
    folder = baseline.run_dir / "references/normalized-probe/00000"
    folder.mkdir(parents=True)
    array = np.arange(16, dtype=np.uint8).reshape(2, 2, 4)
    Image.fromarray(array).save(folder / "original.png")
    debug = baseline.project / "ASTC_Cache/image"
    imported = {"asset": "Assets/a.png", "reference_directory": str(debug)}
    (baseline.run_dir / "probe-imports.jsonl").write_text(json.dumps(imported) + "\n")
    row = {
        "path": "Assets/a.png",
        "width": 2,
        "height": 2,
        "selection": {"candidates_attempted": 1, "block_size": "12x12", "preset": "fastest"},
        "srgb": True,
        "texture_type": "Default",
    }
    captured = {"rows": [row], "capture_provenance": {"synthetic": True}}
    (folder / "parameter_test_report.txt").write_text("12x12 | fastest | 30.03 | 21.57 |")
    ArtifactStore.write_json(folder.parent / "receipt.json", captured)
    option = {
        "astc_file": str(debug / "12x12_fastest.astc"),
        "width": 2,
        "height": 2,
        "channel": 4,
        "quality": 0,
        "need_alpha": True,
        "profile": 0,
        "format_value": 53,
        "format_name": "kTexFormatASTC_12x12",
        "normal_pack": False,
        "rdo": False,
        "rgba_sha256": hashlib.sha256(array[::-1].tobytes()).hexdigest(),
        "input_hash_ms": 0.1,
    }
    return baseline, captured, option


def test_actual_arguments_require_reference_pixels_and_exact_coverage(tmp_path: Path) -> None:
    baseline, captured, option = metadata_fixture(tmp_path)
    log = baseline.run_dir / "probe-options.jsonl"
    log.write_text(json.dumps(option) + "\n")
    result = UnityOptionCapture.audit(baseline, "probe", captured)
    assert result["rows"][0]["need_alpha"] is True
    assert result["candidate_callbacks"] == 1
    option["rgba_sha256"] = "altered"
    log.write_text(json.dumps(option) + "\n")
    with pytest.raises(ValueError, match="RGBA bytes"):
        UnityOptionCapture.audit(baseline, "probe", captured)
    log.write_text("")
    with pytest.raises(ValueError, match="coverage"):
        UnityOptionCapture.audit(baseline, "probe", captured)


def test_metadata_rejects_mismatched_asset_identity(tmp_path: Path) -> None:
    baseline, captured, option = metadata_fixture(tmp_path)
    (baseline.run_dir / "probe-options.jsonl").write_text(json.dumps(option) + "\n")
    captured["rows"][0]["path"] = "Assets/other.png"
    with pytest.raises(ValueError, match="identities"):
        UnityOptionCapture.audit(baseline, "probe", captured)


def test_capture_records_normal_pack_without_claiming_supplement_support(tmp_path: Path) -> None:
    baseline, captured, option = metadata_fixture(tmp_path)
    option["normal_pack"] = True
    captured["rows"][0]["texture_type"] = "NormalMap"
    (baseline.run_dir / "probe-options.jsonl").write_text(json.dumps(option) + "\n")
    result = UnityOptionCapture.audit(baseline, "probe", captured)
    assert result["rows"][0]["normal_pack"] is True
    assert result["rows"][0]["texture_type_importer"] == "NormalMap"


@pytest.mark.parametrize("block,value", [("99x99", 53), ("6x6", 50)])
def test_callback_cannot_substitute_a_different_candidate(
    tmp_path: Path, block: str, value: int
) -> None:
    baseline, captured, option = metadata_fixture(tmp_path)
    option["astc_file"] = str(Path(option["astc_file"]).with_name(f"{block}_fastest.astc"))
    option["format_name"] = f"kTexFormatASTC_{block}"
    option["format_value"] = value
    (baseline.run_dir / "probe-options.jsonl").write_text(json.dumps(option) + "\n")
    with pytest.raises(ValueError, match="footprint/format/profile|omits measured candidates"):
        UnityOptionCapture.audit(baseline, "probe", captured)
