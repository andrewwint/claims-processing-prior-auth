"""The approval service. It never trusts the packet.

The hash proves the stored packet is the one the caller named. The verdict is
rebuilt from trusted sources by the shared checks module. In this change the
trusted sources and the packet store are bundled fixtures; the real stores
replace them in case-packet-and-failure-routing.
"""

import json
from pathlib import Path

import checks

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixtures() -> tuple[dict, dict]:
    trusted = json.loads((FIXTURES / "trusted.json").read_text())
    packets = json.loads((FIXTURES / "packets.json").read_text())["packets"]
    return trusted, packets


def review(packet_id, claimed_hash, *, packets: dict, trusted: dict) -> list[str]:
    """Every reason not to approve. Empty means approve."""
    if not isinstance(packet_id, str) or not isinstance(claimed_hash, str):
        return ["schema: packet_id and packet_hash must be strings"]
    packet = packets.get(packet_id)
    if packet is None:
        return [f"unknown packet: {packet_id}"]
    if checks.packet_hash(packet) != claimed_hash:
        return ["hash mismatch: packet_hash does not match the stored packet"]
    request = trusted["requests"].get(packet.get("case_id")) if isinstance(packet, dict) else None
    if request is None:
        return ["no request record for this packet's case"]
    criteria = trusted["criteria"].get(request["payer_id"], {}).get(request["cpt_code"], [])
    verdict = checks.recompute(packet, request, criteria, trusted["chart"])
    if verdict.approvable:
        return []
    return verdict.failures + [f"criterion not met: {c}" for c in verdict.gaps]
