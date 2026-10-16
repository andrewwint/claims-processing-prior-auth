"""Transaction Search is account-wide: record it before enabling, restore it at teardown.

The record that restore() uses is local and keyed by account, so a clone of this
public repository never applies someone else's settings. A redacted copy is
committed as evidence.
"""

import hashlib
import json
from pathlib import Path

LOCAL_DIR = Path(".local")
EVIDENCE = Path("evidence/account-settings/transaction-search-before.json")


def record_path(account_id: str, base: Path = LOCAL_DIR) -> Path:
    return base / f"transaction-search-before-{hashlib.sha256(account_id.encode()).hexdigest()[:12]}.json"


def current(xray) -> dict:
    dest = xray.get_trace_segment_destination()
    pages = xray.get_paginator("get_indexing_rules").paginate() if xray.can_paginate("get_indexing_rules") else [xray.get_indexing_rules()]
    rules = {
        r["Name"]: r["Rule"].get("Probabilistic", {}).get("DesiredSamplingPercentage")
        for page in pages
        for r in page["IndexingRules"]
    }
    return {"destination": dest["Destination"], "indexing_percentage": rules}


def record(xray, account_id: str, base: Path = LOCAL_DIR, evidence: Path | None = EVIDENCE) -> dict:
    path = record_path(account_id, base)
    if path.exists():
        raise FileExistsError(f"{path} already holds this account's pre-project values; refusing to overwrite them")
    values = current(xray)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(values, indent=2, sort_keys=True) + "\n")
    if evidence is not None:
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text(json.dumps(values, indent=2, sort_keys=True) + "\n")
    return values


class NoRecord(RuntimeError):
    pass


def _load(account_id: str, base: Path) -> dict:
    path = record_path(account_id, base)
    if not path.exists():
        raise NoRecord(f"no pre-project Transaction Search record for this account ({path})")
    return json.loads(path.read_text())


def restore(xray, account_id: str, base: Path = LOCAL_DIR) -> dict:
    before = _load(account_id, base)
    for name, pct in before["indexing_percentage"].items():
        if pct is not None:
            xray.update_indexing_rule(Name=name, Rule={"Probabilistic": {"DesiredSamplingPercentage": pct}})
    if current(xray)["destination"] != before["destination"]:
        xray.update_trace_segment_destination(Destination=before["destination"])
    return before


def compare(xray, account_id: str, base: Path = LOCAL_DIR) -> tuple[dict | None, dict, bool]:
    """(recorded, now, matches). A missing record for this account never counts as a match."""
    now = current(xray)
    try:
        before = _load(account_id, base)
    except NoRecord:
        return None, now, False
    return before, now, before == now
