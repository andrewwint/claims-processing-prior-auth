"""Transaction Search is account-wide: record it before enabling, restore it at teardown."""

import json
from pathlib import Path

RECORD = Path("evidence/account-settings/transaction-search-before.json")


def current(xray) -> dict:
    dest = xray.get_trace_segment_destination()
    pages = xray.get_paginator("get_indexing_rules").paginate() if xray.can_paginate("get_indexing_rules") else [xray.get_indexing_rules()]
    rules = {
        r["Name"]: r["Rule"].get("Probabilistic", {}).get("DesiredSamplingPercentage")
        for page in pages
        for r in page["IndexingRules"]
    }
    return {"destination": dest["Destination"], "indexing_percentage": rules}


def record(xray, path: Path = RECORD) -> dict:
    if path.exists():
        raise FileExistsError(f"{path} already holds the pre-project values; refusing to overwrite them")
    values = current(xray)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(values, indent=2, sort_keys=True) + "\n")
    return values


def restore(xray, path: Path = RECORD) -> dict | None:
    if not path.exists():
        return None
    before = json.loads(path.read_text())
    for name, pct in before["indexing_percentage"].items():
        if pct is not None:
            xray.update_indexing_rule(Name=name, Rule={"Probabilistic": {"DesiredSamplingPercentage": pct}})
    if current(xray)["destination"] != before["destination"]:
        xray.update_trace_segment_destination(Destination=before["destination"])
    return before


def compare(xray, path: Path = RECORD) -> tuple[dict | None, dict, bool]:
    """(recorded, now, matches). Nothing recorded means the setting was never changed."""
    now = current(xray)
    if not path.exists():
        return None, now, True
    before = json.loads(path.read_text())
    return before, now, before == now
