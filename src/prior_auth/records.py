"""Builders for the recommendation and decision records (evidence-record-and-trace D1).

Timestamps are server-generated here; any timestamp in a packet or model output is ignored.
"""

import uuid
from datetime import datetime, timezone

from prior_auth.checks import canonical_hash

STANDARD_WINDOW_S = 7 * 24 * 3600
EXPEDITED_WINDOW_S = 72 * 3600


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_run_id(received_at: str) -> str:
    return received_at.replace(":", "").replace("-", "").replace("+0000", "Z") + "-" + uuid.uuid4().hex[:8]


def recommendation_record(*, case_id: str, run_id: str, packet: dict, decision: dict, policy_version: str | None,
                          received_at: str, recommended_at: str) -> dict:
    return {
        "record_type": "recommendation", "case_id": case_id, "run_id": run_id,
        "packet_id": packet["packet_id"], "packet_hash": canonical_hash(packet),
        "recommendation": decision,
        "citations": [{k: f[k] for k in ("criterion_id", "doc_id", "page", "line")} for f in packet["findings"]],
        "policy_version": policy_version,
        "received_at": received_at, "recommended_at": recommended_at,
    }


def decision_record(*, case_id: str, run_id: str, decision: str, reason: str | None, reviewer_identity: str,
                    reviewer_identity_source: str, recommendation_key: str, recommendation_record_hash: str,
                    decided_at: str) -> dict:
    return {
        "record_type": "decision", "case_id": case_id, "run_id": run_id, "decision": decision, "reason": reason,
        "reviewer_identity": reviewer_identity, "reviewer_identity_source": reviewer_identity_source,
        "recommendation_key": recommendation_key, "recommendation_record_hash": recommendation_record_hash,
        "decided_at": decided_at,
    }


def elapsed_seconds(received_at: str, decided_at: str) -> int:
    start = datetime.fromisoformat(received_at)
    end = datetime.fromisoformat(decided_at)
    return int((end - start).total_seconds())


def within_window(received_at: str, decided_at: str, expedited: bool = False) -> bool:
    return elapsed_seconds(received_at, decided_at) <= (EXPEDITED_WINDOW_S if expedited else STANDARD_WINDOW_S)
