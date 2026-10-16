"""The approval service. It never trusts the packet.

The hash proves the stored packet is the one the caller named. The verdict is
rebuilt from trusted sources by the shared checks module. In this change the
trusted sources and the packet store are bundled fixtures; the real stores
replace them in case-packet-and-failure-routing.
"""

import json
from pathlib import Path

from prior_auth import checks

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixtures() -> tuple[dict, dict]:
    trusted = json.loads((FIXTURES / "trusted.json").read_text())
    packets = json.loads((FIXTURES / "packets.json").read_text())["packets"]
    return trusted, packets


def case_for(packet_id: str, trusted: dict) -> str | None:
    return trusted.get("packet_index", {}).get(packet_id)


def review(packet_id, claimed_hash, *, packets: dict, trusted: dict) -> list[str]:
    """Every reason not to approve. Empty means approve."""
    if not isinstance(packet_id, str) or not isinstance(claimed_hash, str):
        return ["schema: packet_id and packet_hash must be strings"]
    packet = packets.get(packet_id)
    if packet is None:
        return [f"unknown packet: {packet_id}"]
    if checks.packet_hash(packet) != claimed_hash:
        return ["hash mismatch: packet_hash does not match the stored packet"]
    # The packet store's own index, written server-side, says which case a packet
    # belongs to. The packet's claimed case must agree; the packet never chooses.
    case_id = trusted.get("packet_index", {}).get(packet_id)
    if case_id is None:
        return [f"packet {packet_id} is not in the packet store's index"]
    if not isinstance(packet, dict) or packet.get("packet_id") != packet_id or packet.get("case_id") != case_id:
        return ["packet identity does not match the packet store's index"]
    request = trusted["requests"].get(case_id)
    if request is None:
        return ["no request record for this packet's case"]
    criteria = trusted["criteria"].get(request["payer_id"], {}).get(request["cpt_code"], [])
    verdict = checks.recompute(packet, request, criteria, trusted["chart"])
    if verdict.approvable:
        return []
    return verdict.failures + [f"criterion not met: {c}" for c in verdict.gaps]


def review_stored(packet_id, claimed_hash, load_packet) -> tuple[list[str], str | None]:
    """The live path: the packet comes from the packet store, everything else from
    the trusted stores. Returns (failures, case_id). Empty failures means approve."""
    from prior_auth import stores

    if not isinstance(packet_id, str) or not isinstance(claimed_hash, str) or not packet_id.startswith("PKT-"):
        return ["schema: packet_id and packet_hash must be strings, and packet_id must name a case"], None
    case_id = packet_id.removeprefix("PKT-")
    request = stores.request(case_id)
    if request is None:
        return ["no request record for this packet's case"], None
    packet = load_packet(packet_id)
    if packet is None:
        return [f"unknown packet: {packet_id}"], None
    if checks.packet_hash(packet) != claimed_hash:
        return ["hash mismatch: packet_hash does not match the stored packet"], None
    if not isinstance(packet, dict) or packet.get("packet_id") != packet_id or packet.get("case_id") != case_id:
        return ["packet identity does not match its key"], None
    criteria = stores.criteria(request["payer_id"], request["cpt_code"])
    cited = {f.get("doc_id") for f in packet.get("findings", []) if isinstance(f, dict)}
    chart = {"docs": stores.documents(d for d in cited if isinstance(d, str)), "index": stores.chart_index()}
    verdict = checks.recompute(packet, request, criteria, chart)
    if verdict.approvable:
        return [], case_id
    return verdict.failures + [f"criterion not met: {c}" for c in verdict.gaps], case_id
