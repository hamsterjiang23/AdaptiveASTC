"""Freeze human-rating strata and build blind paired-image review packets."""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path

from PIL import Image

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_tile_archive import UnityTileArchive
from adaptive_astc.data.unity_tile_errors import UnityTileViews
from adaptive_astc.evaluation.unity_dense_screening import UnityDenseScreening
from adaptive_astc.utils.artifacts import ArtifactStore as A


class UnityDenseReview:
    SALT = "unity-v5-review-group-split-20261119"
    STRATA = ("calibration", "holdout", "illustration")
    QUEUE_NAMES = {
        "dense": "稠密预测",
        "exact_tile_psnr": "真实小块 PSNR",
        "fixed_rule_selected_exact_tiles": "原规则选中配置",
        "l_p95_primary": "亮度步进",
        "exact_smooth_tile_psnr": "平滑区真实小块 PSNR",
        "known_examples": "已知案例",
    }

    def __init__(self, archive: UnityTileArchive) -> None:
        self.archive = archive
        self.rows = archive.splits["validation"]

    @staticmethod
    def group(row: JsonDict) -> str:
        return row["group"].replace("\\", "/").casefold()

    def partition(self) -> JsonDict:
        examples = {self.group(self.rows[i]) for i in UnityDenseScreening.KNOWN}
        strata: dict[str, list[JsonDict]] = {stage: [] for stage in self.STRATA}
        for row in self.rows:
            if not row["import_metadata"]["srgb"] or row["metadata"]["is_normal"]:
                continue
            group = self.group(row)
            digest = hashlib.sha256(f"{self.SALT}\n{group}".encode()).digest()
            stratum = "illustration" if group in examples else self.STRATA[digest[0] % 2]
            strata[stratum].append({"index": row["index"], "group": group, "asset": row["path"]})
        groups = {key: {row["group"] for row in items} for key, items in strata.items()}
        if any(
            groups[a] & groups[b]
            for a, b in (
                ("calibration", "holdout"),
                ("calibration", "illustration"),
                ("holdout", "illustration"),
            )
        ):
            raise ValueError("Rating partitions share an asset parent directory")
        return {
            "schema": "unity-v5-review-partition-v1",
            "salt": self.SALT,
            "scope": "Development sRGB validation; disjoint recorded parent directories",
            "counts": {key: len(rows) for key, rows in strata.items()},
            "group_counts": {key: len(value) for key, value in groups.items()},
            "development_corpus_sha256": self.archive.sha256,
            "strata": strata,
            "confirmation_opened": False,
        }

    @staticmethod
    def choose(report: JsonDict) -> dict[str, list[int]]:
        """Nominate comparable Top-20 lists without exposing method to reviewers."""
        content = report["reports"]["display@30:content"]["rankings"]
        smooth = report["reports"]["display@30:smooth"]["rankings"]["exact_tile_psnr"]
        return {
            name: [row["index"] for row in ranks["top20"]]
            for name, ranks in (
                *content.items(),
                ("exact_smooth_tile_psnr", smooth),
            )
        }

    def packet(
        self,
        output: Path,
        screening: UnityDenseScreening,
        partition: JsonDict,
        dense: list[JsonDict],
        step: list[JsonDict],
    ) -> JsonDict:
        if partition != self.partition():
            raise ValueError("Frozen rating assignment differs from the V5 development cohort")
        output.mkdir(parents=True, exist_ok=False)
        manifest = {}
        for stratum in self.STRATA:
            allowed = {row["index"] for row in partition["strata"][stratum]}
            queues: dict[str, list[int]]
            if stratum == "illustration":
                queues = {"known_examples": list(UnityDenseScreening.KNOWN)}
            else:
                active = [row for row in dense if row["index"] in allowed]
                scores = [row for row in step if row["index"] in allowed]
                queues = self.choose(screening.compare(active, scores))
            indices = sorted({index for items in queues.values() for index in items})
            if not set(indices).issubset(allowed):
                raise ValueError("Rating queue crossed a frozen partition")
            manifest[stratum] = self.render(output / stratum, indices, queues)
        return manifest

    def render(self, output: Path, indices: list[int], queues: dict[str, list[int]]) -> JsonDict:
        output.mkdir()
        assets = output / "pairs"
        assets.mkdir()
        records = []
        blocks = []
        for index in indices:
            item = self.archive.image("validation", index)
            candidate = item.candidates[self.archive.GRID.index((8, "fastest"))]
            alpha = item.row["actual_options"]["need_alpha"]
            reference = UnityTileViews.display(item.reference(), alpha)
            decoded = UnityTileViews.display(item.decode(candidate), alpha)
            paths = [assets / f"{index:04d}-{kind}.png" for kind in ("reference", "decoded")]
            for path, pixels in zip(paths, (reference, decoded), strict=True):
                Image.fromarray(pixels).save(path)
            label = f"{index:04d}"
            width, height = item.row["width"], item.row["height"]
            blocks.append(
                f'<section id="{label}"><h2>{label} · {width}×{height}</h2><div class="pair">'
                + "".join(
                    f"<figure><figcaption>{title}</figcaption>"
                    f'<img src="pairs/{path.name}" loading="lazy" alt="{label} {title}"></figure>'
                    for path, title in zip(paths, ("参考图", "ASTC 8×8 fastest"), strict=True)
                )
                + "</div></section>"
            )
            records.append(
                {
                    "id": label,
                    "index": index,
                    "asset": item.row["path"],
                    "reference_sha256": item.row["reference_sha256"],
                    "decoded_sha256": candidate["decoded_png_sha256"],
                    "display_sha256": {path.name: A.sha256_file(path) for path in paths},
                }
            )
        rating = output / "ratings.csv"
        with rating.open("x", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(("id", "visible_gradient_banding", "comment"))
            writer.writerows((r["id"], "", "") for r in records)
        page = output / "index.html"
        page.write_text(
            '<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            "<title>渐变台阶复核</title><style>"
            "body{font:16px system-ui,sans-serif;background:#eceef0;color:#17212a;margin:32px}"
            "section{border-top:1px solid #b7c1ca;margin-top:32px}.pair{display:flex;gap:12px;"
            "overflow:auto}figure{margin:0;flex:none}figcaption{margin:8px 0}img{display:block}"
            "</style><h1>渐变台阶复核</h1>"
            "<p>按原始尺寸对比两张图，判断压缩是否在原本平滑的颜色渐变处引入可见台阶。"
            '请在 <a href="ratings.csv">ratings.csv</a> 中填写 yes、no 或 uncertain。'
            "宽图可横向滚动。"
            "</p>" + "".join(blocks) + "</html>",
            encoding="utf-8",
        )
        comparison = output / "queues.html"
        headers = "".join(f"<th>{self.QUEUE_NAMES[key]}</th>" for key in queues)
        table = []
        for rank in range(max(map(len, queues.values()))):
            cells = []
            for choices in queues.values():
                if rank >= len(choices):
                    cells.append("<td></td>")
                else:
                    label = f"{choices[rank]:04d}"
                    cells.append(f'<td><a href="index.html#{label}">{label}</a></td>')
            table.append(f"<tr><th>{rank + 1}</th>{''.join(cells)}</tr>")
        comparison.write_text(
            '<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
            "<title>各方法 Top-20</title><style>"
            "body{font:16px system-ui;margin:32px}table{border-collapse:collapse}"
            "th,td{padding:8px;text-align:left;border-bottom:1px solid #ddd}"
            "</style><h1>各方法 Top-20</h1><p>完成盲评后查看各方法的入选顺序。</p>"
            f"<table><thead><tr><th>名次</th>{headers}</tr></thead>"
            f"<tbody>{''.join(table)}</tbody></table></html>",
            encoding="utf-8",
        )
        return {
            "rows": records,
            "nominated_indices": queues,
            "page_sha256": A.sha256_file(page),
            "comparison_sha256": A.sha256_file(comparison),
            "blank_ratings_sha256": A.sha256_file(rating),
        }
