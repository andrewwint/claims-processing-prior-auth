"""Case packets: canonical hash and the server-side checks behind record_approval."""

import hashlib
import json
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "packets.json"
REQUIRED = ("packet_id", "patient_id", "policy_version", "criteria", "sources")
CRITERION_REQUIRED = ("criterion", "status", "evidence", "source_id")


def packet_hash(packet: dict) -> str:
    canonical = json.dumps(packet, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def load_fixture(path: Path = FIXTURE) -> dict[str, dict]:
    return json.loads(path.read_text())["packets"]


def check_failures(packet: dict) -> list[str]:
    """Every reason this packet may not be approved. Empty means approvable."""
    missing = [k for k in REQUIRED if k not in packet]
    if missing:
        return [f"schema: missing {', '.join(missing)}"]
    failures = []
    sources = packet["sources"]
    if not packet["criteria"]:
        failures.append("schema: no criteria")
    for c in packet["criteria"]:
        absent = [k for k in CRITERION_REQUIRED if k not in c]
        if absent:
            failures.append(f"schema: criterion missing {', '.join(absent)}")
            continue
        name = c["criterion"]
        if c["status"] != "Met":
            failures.append(f"criterion not met: {name}")
            continue
        source = sources.get(c["source_id"])
        if source is None:
            failures.append(f"source match: {name} cites unknown source {c['source_id']}")
        elif c["evidence"] not in source["text"]:
            failures.append(f"source match: {name} evidence not found in {c['source_id']}")
        elif source["patient_id"] != packet["patient_id"]:
            failures.append(f"same patient: {name} cites another patient's record")
    return failures


def verify_for_approval(packets: dict[str, dict], packet_id: str, claimed_hash: str) -> list[str]:
    packet = packets.get(packet_id)
    if packet is None:
        return [f"unknown packet: {packet_id}"]
    if packet_hash(packet) != claimed_hash:
        return ["hash mismatch: packet_hash does not match the stored packet"]
    return check_failures(packet)
