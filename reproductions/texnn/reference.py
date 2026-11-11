"""Build the historical Arm reference codec without modifying its pinned checkout."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from reproductions.common.upstream import EncoderSource


class TexNNReference(EncoderSource):
    def __init__(self, root: Path) -> None:
        super().__init__(
            root / "reproductions/texnn",
            root / "experiment report/.local/reproduction-binaries/texnn",
        )

    def build(self) -> Path:
        commit = self.verify()
        self._archive_previous_build()
        build_dir = self.artifact_dir / "build"
        build_dir.mkdir(parents=True, exist_ok=True)
        original = (self.source / "Source/astc_toplevel.cpp").read_text(encoding="utf-8")
        call = (
            "compress_symbolic_block(input_image, decode_mode, xdim, ydim, zdim, ewp, &pb, &scb);"
        )
        include = '#include "astc_codec_internals.h"'
        if original.count(call) != 1 or original.count(include) != 1:
            raise ValueError("Historical encoder label hook anchors changed")
        generated = build_dir / "generated/astc_toplevel.cpp"
        generated.parent.mkdir(parents=True, exist_ok=True)
        patched = original.replace(include, include + '\n#include "labels.h"')
        patched = patched.replace(
            call,
            call + "\ntexnn_export_block(input_image, xdim, ydim, zdim, ewp, &pb, &scb);",
        )
        generated.write_text(patched, encoding="utf-8")
        prediction_top = original.replace(include, include + '\n#include "prediction.h"')
        prediction_top = prediction_top.replace(
            call,
            "if (!texnn_process_block(input_image, decode_mode, xdim, ydim, zdim, "
            "ewp, &pb, &scb)) { " + call + " }\ntexnn_record_decision(&pb, &scb);",
        )
        store_call = (
            "encode_astc_image(input_image, NULL, xdim, ydim, zdim, ewp, decode_mode, "
            "swz_encode, swz_encode, buffer, 0, threadcount);"
        )
        if prediction_top.count(store_call) != 1:
            raise ValueError("Historical feature-pass hook anchor changed")
        prediction_top = prediction_top.replace(
            store_call,
            store_call + "\nif (texnn_feature_pass()) { "
            "end_coding_time = get_time(); free(buffer); return; }",
        )
        (generated.parent / "astc_predict_toplevel.cpp").write_text(
            prediction_top, encoding="utf-8"
        )
        compression = (self.source / "Source/astc_compress_symbolic.cpp").read_text(
            encoding="utf-8"
        )
        mode_guard = (
            "if (bsd->block_modes[i].permit_encode == 0 || bsd->block_modes[i].is_dual_plane"
        )
        endpoint_function = "determine_optimal_set_of_endpoint_formats_to_use("
        if (
            compression.count(include) != 1
            or compression.count(mode_guard) != 2
            or compression.count(endpoint_function) != 2
        ):
            raise ValueError("Historical predicted-configuration anchors changed")
        compression = compression.replace(include, include + '\n#include "prediction.h"')
        compression = compression.replace(
            mode_guard,
            "if (!texnn_weight_mode_allowed(i) || bsd->block_modes[i].permit_encode == 0 "
            "|| bsd->block_modes[i].is_dual_plane",
        )
        compression = compression.replace(endpoint_function, "texnn_select_endpoint_formats(")
        compression += '\n#include "solver.inc"\n'
        (generated.parent / "astc_predict_compress.cpp").write_text(compression, encoding="utf-8")
        commands = [
            [
                "cmake",
                "-S",
                str(self.method_dir),
                "-B",
                str(build_dir),
                "-G",
                "Visual Studio 17 2022",
                "-A",
                "x64",
            ],
            ["cmake", "--build", str(build_dir), "--config", "Release", "--parallel", "4"],
        ]
        with (self.artifact_dir / "build.log").open("w", encoding="utf-8") as log:
            for command in commands:
                subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
        executable = build_dir / "Release/texnn-reference.exe"
        receipt = {
            "commit": commit,
            "commands": commands,
            "executable": str(executable),
            "sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
            "labels_executable": str(build_dir / "Release/texnn-labels.exe"),
            "labels_sha256": hashlib.sha256(
                (build_dir / "Release/texnn-labels.exe").read_bytes()
            ).hexdigest(),
            "prediction_executable": str(build_dir / "Release/texnn-predict.exe"),
            "prediction_sha256": hashlib.sha256(
                (build_dir / "Release/texnn-predict.exe").read_bytes()
            ).hexdigest(),
            "feature_protocol": "partition_single_plane_rgb24_v2",
            "generated_toplevel_sha256": hashlib.sha256(generated.read_bytes()).hexdigest(),
            "labels_source_sha256": hashlib.sha256(
                (self.method_dir / "native/labels.cpp").read_bytes()
            ).hexdigest(),
            "cmake_sha256": hashlib.sha256(
                (self.method_dir / "CMakeLists.txt").read_bytes()
            ).hexdigest(),
            "native_sources_sha256": {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted((self.method_dir / "native").iterdir())
                if path.is_file()
            },
        }
        (self.artifact_dir / "build-receipt.json").write_text(
            json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
        )
        return executable

    def _archive_previous_build(self) -> None:
        previous = self.artifact_dir / "build-receipt.json"
        if not previous.exists():
            return
        contents = previous.read_bytes()
        receipt = json.loads(contents)
        archive = self.artifact_dir / "history" / hashlib.sha256(contents).hexdigest()
        archive.mkdir(parents=True, exist_ok=True)
        (archive / "original-build-receipt.json").write_bytes(contents)
        manifest = {}
        for path_key, hash_key in [
            ("executable", "sha256"),
            ("labels_executable", "labels_sha256"),
            ("prediction_executable", "prediction_sha256"),
        ]:
            if path_key not in receipt:
                continue
            source = Path(receipt[path_key])
            target = archive / source.name
            expected = receipt[hash_key]
            if not target.exists() and source.exists():
                if hashlib.sha256(source.read_bytes()).hexdigest() == expected:
                    shutil.copy2(source, target)
            valid = target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == expected
            manifest[path_key] = {"path": str(target), "sha256": expected, "verified": valid}
        (archive / "archive.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
