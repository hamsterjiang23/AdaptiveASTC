"""Audit original Unity choices using archived complete candidate quality."""

import argparse
from pathlib import Path

from reproductions.unity_search_baseline.policy_audit import UnityPolicyAudit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    result = UnityPolicyAudit(parser.parse_args().config).run()
    print({key: result[key] for key in ["status", "images", "mismatches", "branch_counts"]})


if __name__ == "__main__":
    main()
