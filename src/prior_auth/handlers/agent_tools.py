"""Lambda target for the agent's case tools.

The three gathering tools read only the trusted stores. route_to_reviewer is
called by decide() alone (never by the model); its queue writer arrives with
evidence-record-and-trace.
"""

import json
import logging
import os

import boto3

from prior_auth import evidence_store, records, stores
from prior_auth.handlers.schemas import CASE_TOOLS

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DELIMITER = "___"
TOOL_NAMES = {t["name"] for t in CASE_TOOLS}


def tool_name(context) -> str:
    full = context.client_context.custom["bedrockAgentCoreToolName"]
    return full[full.index(DELIMITER) + len(DELIMITER):]


def check_eligibility(event: dict) -> dict:
    member = stores.eligibility().get(event.get("member_id"))
    if member is None:
        return {"eligible": False, "reason": "member not found"}
    covered = event.get("cpt_code") in member["covered_cpt"]
    return {"eligible": covered, "payer_id": member["payer_id"], "plan": member["plan"],
            "coverage_start": member["coverage_start"], "coverage_end": member["coverage_end"],
            "reason": None if covered else "service not covered"}


def fetch_policy_criteria(event: dict) -> dict:
    crit = stores.criteria(event.get("payer_id", ""), event.get("cpt_code", ""))
    if not crit:
        return {"verified_policy": False, "criteria": []}
    return {"verified_policy": True, "policy_version": crit[0]["policy_version"],
            "criteria": [{"id": c["id"], "text": c["text"]} for c in crit]}


def extract_clinical_evidence(event: dict) -> dict:
    """The case's documents, line by line with page and line numbers, for the agent to cite."""
    case = stores.cases().get(event.get("case_id"))
    if case is None:
        return {"documents": [], "reason": "case not found"}
    docs = stores.documents(case["documents"])
    return {"documents": [
        {"doc_id": doc_id, "kind": d["kind"],
         "lines": [{"page": p, "line": n, "text": text}
                   for p, page in enumerate(d["pages"], start=1) for n, text in enumerate(page, start=1)]}
        for doc_id, d in docs.items()]}


def route_to_reviewer(event: dict, s3=None) -> dict:
    """Write the queue entry for the clinician (queue/<case_id>.json), pointing at the run's recommendation."""
    entry = {"case_id": event.get("case_id"), "run_id": event.get("run_id"), "reason": event.get("reason"),
             "gaps": event.get("gaps", []), "queued_at": records.now()}
    bucket = os.environ.get("EVIDENCE_BUCKET")
    if bucket and isinstance(entry["case_id"], str):
        evidence_store.put_queue_entry(s3 or boto3.client("s3"), bucket, entry)
    return {"routed": True, **{k: entry[k] for k in ("case_id", "run_id", "reason", "gaps")}}


TOOLS = {"check_eligibility": check_eligibility, "fetch_policy_criteria": fetch_policy_criteria,
         "extract_clinical_evidence": extract_clinical_evidence, "route_to_reviewer": route_to_reviewer}


def handler(event, context):
    name = tool_name(context)
    if name not in TOOL_NAMES:
        return {"error": f"unknown tool: {name}"}
    result = TOOLS[name](event)
    # Identifiers only; chart text never goes to the logs.
    logger.info(json.dumps({"tool": name, "case_id": event.get("case_id")}))
    return result
