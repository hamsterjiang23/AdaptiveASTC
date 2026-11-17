"""Create V3 evidence bindings and optionally audit the development source images."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from reproductions.unity_search_baseline.v3_evidence import UnityV3Evidence


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-sources", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    tool = UnityV3Evidence(Path(__file__).resolve().parents[1])
    result = tool.audit_sources(smoke=args.smoke) if args.audit_sources else tool.prepare()
    print(json.dumps({key: result[key] for key in ["status", "test_opened"]}, ensure_ascii=True))
    if result["status"] == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
