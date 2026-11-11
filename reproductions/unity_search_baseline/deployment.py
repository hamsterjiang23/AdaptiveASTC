"""Time reference pixels through fresh prediction to one native ASTC encoding per image."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_inference import UnityInferenceInput, UnityInferenceTexture
from adaptive_astc.evaluation.unity_inference import UnityQualityInference
from adaptive_astc.evaluation.unity_quality import UnityQualityPrediction, UnityTextureInput
from reproductions.unity_search_baseline.policy import UnitySearchPolicy
from reproductions.unity_search_baseline.supplement import UnityASTCBackend


@dataclass
class UnityDeploymentResult:
    containers: list[bytes]
    choices: list[JsonDict]
    predictions: dict[str, np.ndarray] | None
    timings: JsonDict


class UnityDeploymentTrial:
    """The measured path accepts pixels/import settings, policies and a trained predictor only."""

    def __init__(
        self,
        textures: list[UnityInferenceTexture],
        policies: list[UnitySearchPolicy],
        backends: list[UnityASTCBackend],
        predictor: UnityQualityInference,
        patch_size: int,
        fixed8_preset: str,
    ) -> None:
        if not textures or len(textures) != len(policies) or len(textures) != len(backends):
            raise ValueError("Every deployment texture needs one policy and native backend")
        if fixed8_preset not in UnityASTCBackend.PRESETS:
            raise ValueError("Explicit fixed8 preset required")
        for texture in textures:
            texture.validate()
        self.textures, self.policies, self.backends = textures, policies, backends
        self.predictor, self.patch_size, self.fixed8_preset = predictor, patch_size, fixed8_preset

    @staticmethod
    def texture_input(pixels: NDArray[np.uint8], spec: UnityInferenceTexture) -> UnityTextureInput:
        height, width = pixels.shape[:2]
        return UnityTextureInput(
            width,
            height,
            spec.srgb,
            spec.normal,
            spec.need_alpha,
            bool(pixels[:, :, 3].min() == pixels[:, :, 3].max()),
            float(np.mean(np.all(pixels[:, :, :3] == 0, axis=2))),
        )

    @staticmethod
    def encode(
        backend: UnityASTCBackend,
        rgba: NDArray[np.uint8],
        block: int,
        preset: str,
        spec: UnityInferenceTexture,
    ) -> tuple[bytes, float]:
        """Use the frozen backend ABI without executing decode in the measured interval."""
        if rgba.dtype != np.uint8 or rgba.ndim != 3 or rgba.shape[2] != 4:
            raise ValueError("Native deployment requires RGBA8")
        height, width = rgba.shape[:2]
        if (
            min(width, height) < 1
            or width * height > 536870911
            or max(width, height) >= 2**24
            or block not in backend.BLOCKS
            or preset not in backend.PRESETS
        ):
            raise ValueError("Invalid deployment image or ASTC candidate")
        reference = np.array(rgba, dtype=np.uint8, order="C", copy=True)
        payload = np.zeros(
            ((width + block - 1) // block) * ((height + block - 1) // block) * 16, dtype=np.uint8
        )
        started = time.perf_counter()
        backend.encode_function(
            reference.ctypes.data,
            width,
            height,
            backend.PRESETS[preset],
            False,
            block,
            payload.ctypes.data,
            0 if spec.srgb else 1,
            False,
            None,
            spec.need_alpha,
            False,
            0.0,
            0,
        )
        seconds = time.perf_counter() - started
        if not payload.any():
            raise RuntimeError("Unity encoder returned an empty deployment payload")
        return backend.container(payload.tobytes(), width, height, block), seconds

    def run(self, *, predicted: bool) -> UnityDeploymentResult:
        if type(predicted) is not bool:
            raise ValueError("Explicit prediction/fixed8 arm required")
        if predicted:
            self.predictor.synchronize()
        started = time.perf_counter()
        predictions, dataset = None, None
        preparation = 0.0
        phases: JsonDict = {}
        if predicted:
            before = time.perf_counter()
            dataset = UnityInferenceInput(self.textures, self.patch_size)
            preparation = time.perf_counter() - before
            predictions, phases = self.predictor.run(dataset)
        containers, choices = [], []
        loading = policy_seconds = encoding = 0.0
        for index, (spec, policy, backend) in enumerate(
            zip(self.textures, self.policies, self.backends, strict=True)
        ):
            before = time.perf_counter()
            if dataset is None:
                with Image.open(spec.reference) as image:
                    pixels = np.asarray(image.convert("RGBA"), dtype=np.uint8)
            else:
                pixels = dataset.pixels(index)
            rgba = np.ascontiguousarray(pixels[::-1])
            loading += time.perf_counter() - before
            before = time.perf_counter()
            if predictions is not None:
                choice = asdict(
                    UnityQualityPrediction.select(
                        policy,
                        self.texture_input(pixels, spec),
                        predictions["channel_mse"][index],
                        predictions["channel_zero"][index],
                        predictions["image_quality"][index],
                    )
                )
                selected = choice["selected_index"]
            else:
                selected = UnityQualityPrediction.GRID.index((8, self.fixed8_preset))
                choice = {"selected_index": selected}
            block, preset = UnityQualityPrediction.GRID[selected]
            policy_seconds += time.perf_counter() - before
            container, seconds = self.encode(backend, rgba, block, preset, spec)
            containers.append(container)
            choices.append(choice)
            encoding += seconds
        if predicted:
            self.predictor.synchronize()
        elapsed = time.perf_counter() - started
        return UnityDeploymentResult(
            containers,
            choices,
            predictions,
            {
                "end_to_end_seconds": elapsed,
                "reference_and_metadata_seconds": preparation,
                "reference_load_and_flip_seconds": loading,
                "inference": phases,
                "policy_seconds": policy_seconds,
                "native_encode_seconds": encoding,
                "encoding_calls": len(containers),
                "images": len(self.textures),
                "scope": (
                    "Reference PNG to in-memory mip0 ASTC; "
                    "excludes model/DLL load, audit and writes"
                ),
            },
        )
