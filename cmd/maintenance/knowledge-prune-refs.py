#!/usr/bin/env python3
"""Fail-closed Open WebUI Knowledge-reference inventory for upload pruning.

Open WebUI 0.12.5 exposes paginated Knowledge bases and, separately, paginated
files for each base. Never infer 'unreferenced' from an incomplete API result.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


class InventoryError(RuntimeError):
    pass


def require_page(data: object) -> tuple[list[dict], int]:
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise InventoryError("Knowledge pagination is missing an items list")
    total = data.get("total")
    if isinstance(total, bool) or not isinstance(total, int) or total < 0:
        raise InventoryError("Knowledge pagination has no trustworthy total")
    items = data["items"]
    if any(not isinstance(item, dict) or not isinstance(item.get("id"), str)
           or not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", item["id"]) for item in items):
        raise InventoryError("Knowledge pagination contains an invalid identifier")
    return items, total


def inventory(base: str, key: str) -> tuple[set[str], int]:
    if not base.startswith(("http://127.0.0.1:", "http://localhost:")):
        raise InventoryError("Knowledge pruning requires a loopback Open WebUI URL")

    def get(path: str) -> object:
        request = Request(base.rstrip("/") + path, headers={
            "Authorization": "Bearer " + key,
            "Accept": "application/json",
        })
        try:
            with urlopen(request, timeout=30) as response:
                return json.load(response)
        except (HTTPError, URLError, ValueError, OSError) as exc:
            raise InventoryError(f"Knowledge inventory API request failed: {path}: {exc}") from exc

    def pages(path: str) -> list[dict]:
        found: dict[str, dict] = {}
        expected: int | None = None
        for page in range(1, 10001):
            data, total = require_page(get(f"{path}{'&' if '?' in path else '?'}page={page}"))
            if expected is None:
                expected = total
            if total != expected:
                raise InventoryError("Knowledge list changed while paginating")
            for item in data:
                item_id = item["id"]
                if item_id in found:
                    raise InventoryError("Knowledge list contains duplicate file/base identifiers")
                found[item_id] = item
            if len(found) == expected:
                return list(found.values())
            if not data or len(found) > expected:
                raise InventoryError("Knowledge list ended before advertised total")
        raise InventoryError("Knowledge pagination limit exceeded")

    bases = pages("/api/v1/knowledge/")
    protected: set[str] = set()
    for base_entry in bases:
        # In the matching Open WebUI version each response has items and total.
        files = pages("/api/v1/knowledge/" + quote(base_entry["id"], safe="") + "/files")
        protected.update(item["id"] for item in files)
    return protected, len(bases)


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: knowledge-prune-refs.py <private-output-file>", file=sys.stderr)
        return 2
    try:
        ids, count = inventory(os.environ["OWUI_URL"], os.environ["OWUI_API_KEY"])
        Path(sys.argv[1]).write_text("".join(fid + "\n" for fid in sorted(ids)), encoding="utf-8")
    except (KeyError, InventoryError, OSError) as exc:
        print(f"ERROR: Knowledge-reference inventory incomplete; no deletes permitted: {exc}", file=sys.stderr)
        return 1
    print(f"Protected {len(ids)} Knowledge-linked file IDs across {count} bases.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
