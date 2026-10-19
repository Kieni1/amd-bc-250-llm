from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "release-contract.json"


def load_contract() -> dict:
    data = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if data.get("schema") != "bc250.release-contract.v1":
        raise SystemExit("ERROR: unsupported release-contract schema")
    return data


def get_field(data: dict, dotted: str):
    value = data
    for part in dotted.split("."):
        if not isinstance(value, dict) or part not in value:
            raise SystemExit(f"ERROR: release-contract field not found: {dotted}")
        value = value[part]
    if isinstance(value, (dict, list)):
        print(json.dumps(value, sort_keys=True))
    else:
        print(value)


def print_plan(mode: str, allow_dirty: bool) -> None:
    contract = load_contract()
    validation = contract["validation"]
    key = "full_plan" if mode == "full" else "fast_plan"
    print(f"mode: {mode}")
    for index, stage in enumerate(validation[key], start=1):
        print(f"{index}. {stage['id']} ({stage['description']})")
    if mode == "full":
        if allow_dirty:
            print("qualification: engineering-only dirty source allowed")
        else:
            print("qualification: clean source required for release authority")


def main() -> int:
    parser = argparse.ArgumentParser(description="Read the BC-250 release contract")
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan", help="print a declared build stage plan")
    plan.add_argument("--mode", choices=("fast", "full"), required=True)
    plan.add_argument("--allow-dirty", action="store_true")
    field = sub.add_parser("field", help="print one dotted-path field")
    field.add_argument("path")
    args = parser.parse_args()
    if args.command == "plan":
        print_plan(args.mode, args.allow_dirty)
    elif args.command == "field":
        get_field(load_contract(), args.path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
