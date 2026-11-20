"""Compare dense, exact-error, step, and policy-conditioned review queues."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_tile_archive import UnityTileArchive
from adaptive_astc.utils.artifacts import ArtifactStore as A


class UnityDenseScreening:
    KNOWN = (615, 616, 617)
    BUDGETS = (0.03, 0.05, 0.10)

    def __init__(self, archive: UnityTileArchive, policy_report: Path) -> None:
        self.rows = archive.splits["validation"]
        self.candidate = archive.GRID.index((8, "fastest"))
        policy = A.read_json(policy_report)
        raw_path, raw_sha = Path(policy["raw_receipt"]), policy["raw_receipt_sha256"]
        raw = archive.read_bound_json(raw_path, raw_sha, dict)
        if (
            raw["status"] != "passed"
            or raw["test_opened"] is not False
            or raw["config"]["corpus_sha256"] != archive.sha256
        ):
            raise ValueError("Fixed-rule replay did not use the frozen V5 data handoff")
        replay = raw["rows"]["validation"]["exact_targets"]
        self.grid = archive.GRID
        self.policy_choices: dict[int, int] = {}
        for ref, choice in zip(self.rows, replay, strict=True):
            decision = choice["predicted_decision"]
            idx = decision["selected_index"]
            block, preset = archive.GRID[idx]
            if (
                ref["path"] != choice["path"]
                or not choice["full_choice_match"]
                or (f"{block}x{block}", preset) != (decision["block_size"], decision["preset"])
            ):
                raise ValueError("Fixed-rule replay differs from the frozen image/candidate order")
            self.policy_choices[ref["index"]] = idx
        self.policy_receipt_sha256 = raw_sha

    @staticmethod
    def spearman(first: dict[int, float], second: dict[int, float]) -> float | None:
        ids = sorted(first.keys() & second.keys())
        ranks = []
        for source in (first, second):
            _, inverse, counts = np.unique(
                [source[i] for i in ids],
                return_inverse=True,
                return_counts=True,
            )
            ranks.append((np.cumsum(counts) - (counts - 1) / 2)[inverse])
        if len(ids) < 3 or min(np.ptp(rank) for rank in ranks) == 0:
            return None
        return float(np.corrcoef(ranks)[0, 1])

    @classmethod
    def rank(cls, values: dict[int, float]) -> JsonDict:
        top = sorted(values, key=lambda i: (-values[i], i))[:20]
        return {
            "n": len(values),
            "top20": [{"index": idx, "score": values[idx]} for idx in top],
            "known": {
                str(i): {
                    "score": values[i],
                    "rank": 1 + sum(v > values[i] for v in values.values()),
                    "ties": sum(v == values[i] for v in values.values()) - 1,
                    "in_top20": i in top,
                }
                for i in cls.KNOWN
                if i in values
            },
        }

    def compare(self, dense_rows: list[JsonDict], step_rows: list[JsonDict]) -> JsonDict:
        steps = {row["index"]: row for row in step_rows}
        for image, row in steps.items():
            source = self.rows[image]
            if (
                row["asset"] != source["path"]
                or row["reference_sha256"] != source["reference_sha256"]
            ):
                raise ValueError("Step baseline asset or reference changed")
        scope = {r["index"] for r in dense_rows if r["index"] in steps}
        if not scope or len({r["index"] for r in dense_rows}) != len(dense_rows):
            raise ValueError("Require nonempty unique dense validation coverage")
        matched_psnr35 = {
            i
            for i in scope
            if steps[i]["native_psnr"] >= 35 and steps[i]["l_p95_primary"] is not None
        }
        results, psnr35_results = {}, {}
        for y in (28, 30):
            for region in ("all", "content", "smooth"):
                key = f"display@{y}:{region}"
                results[key] = self.compare_one(dense_rows, steps, scope, y, region)
                psnr35_results[key] = self.compare_one(dense_rows, steps, matched_psnr35, y, region)
        return {
            "scope": "native sRGB development images covered by both dense outputs and step input",
            "images": len(scope),
            "candidate": [8, "fastest"],
            "reports": results,
            "psnr35_step_valid": {"images": len(matched_psnr35), "reports": psnr35_results},
            "candidate_upgrades": self.upgrade_comparison(dense_rows, scope),
            "policy_replay_raw_receipt_sha256": self.policy_receipt_sha256,
            "human_labels": "awaiting_review",
            "human_gradation_recall": None,
        }

    def compare_one(
        self,
        dense_rows: list[JsonDict],
        steps: dict[int, JsonDict],
        scope: set[int],
        y: int,
        region: str,
    ) -> JsonDict:
        pred: dict[int, float] = {}
        true: dict[int, float] = {}
        fixed: dict[int, float] = {}
        for row in dense_rows:
            idx, count = row["index"], row["regions"][region]
            if idx not in scope or count == 0:
                continue
            bad = row["bad"]["display"][str(y)][region]
            pred[idx] = bad["predicted"][self.candidate] / count
            true[idx] = bad["true"][self.candidate] / count
            fixed[idx] = bad["true"][self.policy_choices[idx]] / count
        step = {
            i: float(steps[i]["l_p95_primary"])
            for i in true
            if steps[i]["l_p95_primary"] is not None
        }
        ranked = {
            name: self.rank(values)
            for name, values in (
                ("dense", pred),
                ("exact_tile_psnr", true),
                ("fixed_rule_selected_exact_tiles", fixed),
                ("l_p95_primary", step),
            )
        }
        top = {k: {row["index"] for row in v["top20"]} for k, v in ranked.items()}
        matched_idx = set(step)
        common = {
            name: self.rank({i: values[i] for i in matched_idx})
            for name, values in (
                ("dense", pred),
                ("exact_tile_psnr", true),
                ("fixed_rule_selected_exact_tiles", fixed),
            )
        }
        common_top = {k: {row["index"] for row in v["top20"]} for k, v in common.items()}
        oracle_top = top["exact_tile_psnr"]
        overlap = len(top["dense"] & oracle_top)
        return {
            "rankings": ranked,
            "dense_exact_top20_overlap": overlap,
            "dense_exact_top20_recall": overlap / len(oracle_top) if oracle_top else None,
            "step_matched_images": len(matched_idx),
            "step_matched_top20_overlap": {
                key: len(ids & top["l_p95_primary"]) for key, ids in common_top.items()
            },
            "dense_vs_exact_spearman": self.spearman(pred, true),
            "step_vs_exact_spearman": self.spearman(step, true),
            "native_psnr_vs_exact_spearman": self.spearman(
                {i: float(steps[i]["native_psnr"]) for i in true}, true
            ),
            "dense_vs_exact_spearman_on_step_matched_images": self.spearman(
                {i: pred[i] for i in matched_idx},
                {i: true[i] for i in matched_idx},
            ),
            "share_grid": {
                str(x): {
                    "dense_flagged": sum(p >= x for p in pred.values()),
                    "exact_flagged": sum(t >= x for t in true.values()),
                    "rule_selected_flagged": sum(t >= x for t in fixed.values()),
                    "dense_exact_agree_positive": sum(pred[i] >= x and true[i] >= x for i in true),
                }
                for x in self.BUDGETS
            },
        }

    def upgrade_comparison(self, dense_rows: list[JsonDict], scope: set[int]) -> JsonDict:
        """Audit whether a predicted improvement across presets survives exact tile scoring."""
        rows = [row for row in dense_rows if row["index"] in scope and row["regions"]["content"]]
        result = {}
        candidates = [(8, "fast"), (8, "thorough"), (6, "fastest")]
        for y in (28, 30):
            if not rows:
                break
            counts = [row["bad"]["display"][str(y)]["content"] for row in rows]
            denom = np.array([row["regions"]["content"] for row in rows])[:, None]
            exact = np.array([count["true"] for count in counts]) / denom
            predicted = np.array([count["predicted"] for count in counts]) / denom
            for block, preset in candidates:
                target = self.grid.index((block, preset))
                true_base, pred_base = exact[:, self.candidate], predicted[:, self.candidate]
                true_target, pred_target = exact[:, target], predicted[:, target]
                delta_error = (pred_target - pred_base) - (true_target - true_base)
                transitions = {}
                for x in self.BUDGETS:
                    found = (pred_base >= x) & (pred_target < x)
                    measured = (true_base >= x) & (true_target < x)
                    transitions[str(x)] = {
                        "predicted": int(found.sum()),
                        "measured": int(measured.sum()),
                        "both": int((found & measured).sum()),
                    }
                result[f"{block}x{block}_{preset}@{y}"] = {
                    "images": len(rows),
                    "true_mean_delta": float((true_target - true_base).mean()),
                    "predicted_mean_delta": float((pred_target - pred_base).mean()),
                    "delta_mae": float(np.abs(delta_error).mean()),
                    "moves_below_bad_share_threshold": transitions,
                }
        return result
