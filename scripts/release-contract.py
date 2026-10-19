from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "release-contract.json"


def load_contract() -> dict:
    data = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if data.get("schema") != "bc250.release-contract.v2":
        raise SystemExit("ERROR: unsupported release-contract schema")
    return data


def get_field(data: dict, dotted: str) -> None:
    value = data
    for part in dotted.split("."):
        if not isinstance(value, dict) or part not in value:
            raise SystemExit(f"ERROR: release-contract field not found: {dotted}")
        value = value[part]
    if isinstance(value, (dict, list)):
        print(json.dumps(value, sort_keys=True))
    else:
        print(value)


def print_plan() -> None:
    contract = load_contract()
    print("producer: GitHub Actions / Fedora 44")
    print("release authority: explicit selected workflow_dispatch run only")
    for index, stage in enumerate(contract["validation"]["stages"], start=1):
        print(f"{index}. {stage['id']} ({stage['description']})")
    print("local execution: backup/reproduction only")


def main() -> int:
    parser = argparse.ArgumentParser(description="Read the BC-250 release contract")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("plan", help="print the declared release stage plan")
    field = sub.add_parser("field", help="print one dotted-path field")
    field.add_argument("path")
    args = parser.parse_args()
    if args.command == "plan":
        print_plan()
    else:
        get_field(load_contract(), args.path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
