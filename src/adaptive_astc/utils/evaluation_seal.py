"""Share test-set locks between probability metrics and compression measurements."""

from pathlib import Path

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore


class EvaluationSeal:
    @staticmethod
    def read(run: Path, fingerprint: str) -> JsonDict:
        path = run / "test_seal.json"
        result = (
            ArtifactStore.read_json(path)
            if path.exists()
            else {"data_fingerprint": fingerprint, "arms": {}}
        )
        if result["data_fingerprint"] != fingerprint or set(result) - {
            "data_fingerprint",
            "arms",
            "compression_models",
        }:
            raise ValueError("Test seal belongs to another dataset or has an unknown schema")
        return result

    @classmethod
    def probabilities(cls, run: Path, fingerprint: str, arms: JsonDict) -> JsonDict:
        previous = cls.read(run, fingerprint)
        if previous["arms"] and previous["arms"] != arms:
            raise ValueError("The locked models/temperatures changed after test opening")
        compression = previous.get("compression_models", {})
        if any(
            name not in arms or arms[name]["checkpoint_sha256"] != digest
            for name, digest in compression.items()
        ):
            raise ValueError("Probability model differs from the sealed compression model")
        result = {"data_fingerprint": fingerprint, "arms": arms}
        if compression:
            result["compression_models"] = compression
        ArtifactStore.write_json(run / "test_seal.json", result)
        return result

    @classmethod
    def compression(cls, run: Path, fingerprint: str, arm: str, checkpoint: str) -> JsonDict:
        result = cls.read(run, fingerprint)
        if result["arms"] and (
            arm not in result["arms"] or result["arms"][arm]["checkpoint_sha256"] != checkpoint
        ):
            raise ValueError("Compression model differs from the sealed probability model")
        models = result.setdefault("compression_models", {})
        if arm in models and models[arm] != checkpoint:
            raise ValueError("Compression test was opened with another model checkpoint")
        models[arm] = checkpoint
        ArtifactStore.write_json(run / "test_seal.json", result)
        return result
