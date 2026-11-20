"""Reserve V5 source identities without importing Unity pixels or opening any test labels."""

import argparse
from pathlib import Path

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_tile_archive import UnityTileArchive
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline.confirmation import UnityConfirmationCohort as Cohort

ROOT = Path(__file__).resolve().parents[1]
HISTORICAL = ROOT / "experiment report/unity-accuracy90-20261111"
RAW = ROOT / "experiment report/.local/unity-v5-20261119"
REPORTS = ROOT / "experiment report/unity-v5-20261119"


def exclusions(config: JsonDict, folder: Path) -> JsonDict:
    archive = UnityTileArchive(HISTORICAL / "unity-v2-data-inputs.json")
    snapshot_meta = config["snapshot"]
    snapshot = archive.read_bound_json(Path(snapshot_meta["path"]), snapshot_meta["sha256"], dict)
    by_asset = {
        Cohort.asset_path(path).casefold(): record["fileHash"].lower()
        for path, record in snapshot["entries"].items()
        if path.replace("\\", "/").casefold().startswith("assets/")
    }
    development = {
        name: [
            {"path": row["path"], "fileHash": by_asset[Cohort.asset_path(row["path"]).casefold()]}
            for row in rows
        ]
        for name, rows in archive.splits.items()
    }
    prior_reports = (
        HISTORICAL / "unity-confirmation2000-v1.json",
        HISTORICAL / "unity-confirmation2000-v2.json",
        ROOT / "experiment report/unity-v2-20261112/confirmation2000-near-revision-v3.json",
    )
    prior_rows: dict[str, list[JsonDict]] = {}
    prior_manifest_sha256 = {}
    for index, evidence in enumerate(prior_reports):
        summary = A.read_json(evidence)
        path, digest = Path(summary["manifest"]), summary["manifest_sha256"]
        reserved = archive.read_bound_json(path, digest, dict)
        if reserved["native_labels_collected"] is not False or reserved["test_opened"] is not False:
            raise ValueError("Use source-only historic confirmation identity manifests")
        prior_manifest_sha256[str(path)] = digest
        prior_rows[f"prior_{index}"] = [
            {"path": row["path"], "fileHash": row["fileHash"]}
            for kind in ("primary", "reserves")
            for row in reserved[kind]
        ]
    projection = folder / "source-exclusions.json"
    A.write_json(
        projection,
        {
            "splits": development | prior_rows,
            "development_corpus_sha256": archive.sha256,
            "prior_source_identity_manifest_sha256": prior_manifest_sha256,
            "snapshot_sha256": snapshot_meta["sha256"],
            "scope": "Source path and MD4 fields only",
        },
    )
    return {"path": str(projection), "sha256": A.sha256_file(projection)}


def verify_reservation(summary: JsonDict, config: JsonDict) -> JsonDict:
    prior: list[JsonDict] = []
    for record in config["excluded_manifests"]:
        manifest = UnityTileArchive.read_bound_json(Path(record["path"]), record["sha256"], dict)
        prior.extend(row for rows in manifest["splits"].values() for row in rows)
    reserved = UnityTileArchive.read_bound_json(
        Path(summary["manifest"]), summary["manifest_sha256"], dict
    )
    selected = reserved["primary"] + reserved["reserves"]
    paths = {Cohort.asset_path(row["path"]).casefold() for row in prior}
    groups = {Cohort.asset_group(Cohort.asset_path(row["path"])) for row in prior}
    md4 = {row["fileHash"].lower() for row in prior}
    checked = [Cohort.asset_path(row["path"]) for row in selected]
    if (
        paths & {path.casefold() for path in checked}
        or groups & {Cohort.asset_group(path) for path in checked}
        or md4 & {row["fileHash"].lower() for row in selected}
        or len(checked) != len({row["fileHash"].lower() for row in selected})
        or len(checked) != len(set(path.casefold() for path in checked))
    ):
        raise ValueError("New source cohort overlaps historical asset, group or MD4 identity")
    image_root = Path(config["image_root"])
    for row, filename in zip(selected, checked, strict=True):
        path = image_root / filename
        if (
            A.sha256_file(path) != row["source_sha256"]
            or A.sha256_file(path.with_name(path.name + ".meta")) != row["meta_sha256"]
        ):
            raise ValueError(f"New cohort source or meta identity changed: {filename}")
    return {
        "status": "passed",
        "reserved_source_identities": len(checked),
        "path_group_and_source_md4_overlaps": 0,
        "source_manifests_checked": len(config["excluded_manifests"]),
        "manifest_sha256": summary["manifest_sha256"],
        "pixel_isolation_verified": False,
        "source_and_meta_sha256_rechecked": True,
        "confirmation_execution_authorized": False,
        "confirmation_opened": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--primary", type=int, default=1000)
    parser.add_argument("--reserves", type=int, default=250)
    args = parser.parse_args()
    if args.primary < 50 or args.reserves < 0:
        parser.error("Require at least 50 primary assets and a nonnegative reserve count")
    tag = (
        "confirmation-source-smoke-v1"
        if args.smoke
        else f"confirmation-source{args.primary}-reserve{args.reserves}-v1"
    )
    configuration = RAW / f"{tag}-configuration"
    configuration.mkdir(parents=True, exist_ok=False)
    config = A.read_json(HISTORICAL / "unity-confirmation2000-v1-config.json")
    config["excluded_manifests"].append(exclusions(config, configuration))
    config.update(
        seed=20261119,
        images=2 if args.smoke else args.primary,
        reserves=2 if args.smoke else args.reserves,
        minimum_groups=1 if args.smoke else 50,
        output=str(RAW / tag),
        report=str(REPORTS / f"{tag}.json"),
    )
    path = configuration / "config.json"
    A.write_json(path, config)
    summary = Cohort(ROOT, path).reserve()
    if summary["status"] != "reserved":
        raise RuntimeError(
            f"Source reservation incomplete: {summary['primary_images']} primary assets"
        )
    verified = verify_reservation(summary, config)
    A.write_json(REPORTS / f"{tag}-verification.json", verified)
    print(f"Reserved and audited {verified['reserved_source_identities']} source identities")


if __name__ == "__main__":
    main()
