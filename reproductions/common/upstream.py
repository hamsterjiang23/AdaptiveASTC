"""Build author encoders while keeping their source version and license intact."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


class EncoderSource:
    def __init__(self, method_dir: Path, artifact_dir: Path) -> None:
        self.method_dir = method_dir.resolve()
        self.source = self.method_dir / "upstream"
        self.artifact_dir = artifact_dir.resolve()

    def fetch(self) -> str:
        if self.source.exists():
            return self.verify()
        metadata = json.loads((self.method_dir / "source.json").read_text(encoding="utf-8"))
        repository = metadata.get("repository", metadata.get("encoder_repository"))
        commit = metadata.get("commit", metadata.get("encoder_commit"))
        subprocess.run(
            ["git", "clone", "--filter=blob:none", "--no-checkout", repository, str(self.source)],
            check=True,
        )
        subprocess.run(["git", "-C", str(self.source), "checkout", "--detach", commit], check=True)
        return self.verify()

    def verify(self) -> str:
        metadata = json.loads((self.method_dir / "source.json").read_text(encoding="utf-8"))
        expected = metadata.get("commit", metadata.get("encoder_commit"))
        actual = subprocess.check_output(
            ["git", "-C", str(self.source), "rev-parse", "HEAD"], text=True
        ).strip()
        if actual != expected:
            raise ValueError(f"Upstream commit mismatch: {actual} != {expected}")
        changes = subprocess.check_output(
            ["git", "-C", str(self.source), "status", "--porcelain"], text=True
        )
        if changes.strip():
            raise ValueError("Author encoder has local modifications; record a patch first")
        return actual

    def build(self) -> Path:
        commit = self.verify()
        build_dir = self.artifact_dir / "build"
        build_dir.mkdir(parents=True, exist_ok=True)
        cmake_source = (self.source / "CMakeLists.txt").read_text(encoding="utf-8")
        prefix = "ASTCENC_" if "option(ASTCENC_ISA_AVX2" in cmake_source else ""
        commands = [
            [
                "cmake",
                "-S",
                str(self.source),
                "-B",
                str(build_dir),
                "-G",
                "Visual Studio 17 2022",
                "-A",
                "x64",
                f"-D{prefix}ISA_AVX2=ON",
                f"-D{prefix}ISA_SSE41=OFF",
                f"-D{prefix}ISA_SSE2=OFF",
                f"-D{prefix}ISA_NATIVE=OFF",
            ],
            ["cmake", "--build", str(build_dir), "--config", "Release", "--parallel", "4"],
        ]
        with (self.artifact_dir / "build.log").open("w", encoding="utf-8") as log:
            for command in commands:
                subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
        matches = list(build_dir.rglob("astcenc-avx2.exe"))
        if len(matches) != 1:
            raise RuntimeError(f"Expected one encoder executable, found {matches}")
        executable = matches[0]
        receipt = {
            "commit": commit,
            "commands": commands,
            "executable": str(executable),
            "sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        }
        (self.artifact_dir / "build-receipt.json").write_text(
            json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
        )
        return executable


class BaselineGate:
    @staticmethod
    def require(receipt_path: Path) -> None:
        if not receipt_path.is_file():
            raise RuntimeError(
                "Complete the 10000-image Unity search baseline before image experiments"
            )
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if receipt.get("status") != "passed" or receipt.get("phase") != "full":
            raise RuntimeError("Formal literature experiments require a passed full Unity baseline")
        if (
            receipt.get("expected") != 10_000
            or receipt.get("imports") != 10_000
            or receipt.get("native_records") != 10_000
            or receipt.get("process_exit_code") != 0
            or receipt.get("metadata_restore_conflicts") != []
            or receipt.get("provenance", {}).get("source_hashes_verified") != 10_000
        ):
            raise RuntimeError("Baseline coverage must include all 10000 training images")
