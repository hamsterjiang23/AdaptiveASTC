"""Build the historical Arm reference codec without modifying its pinned checkout."""

from __future__ import annotations

import hashlib
import json
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
            "generated_toplevel_sha256": hashlib.sha256(generated.read_bytes()).hexdigest(),
            "labels_source_sha256": hashlib.sha256(
                (self.method_dir / "native/labels.cpp").read_bytes()
            ).hexdigest(),
            "cmake_sha256": hashlib.sha256(
                (self.method_dir / "CMakeLists.txt").read_bytes()
            ).hexdigest(),
        }
        (self.artifact_dir / "build-receipt.json").write_text(
            json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
        )
        return executable
