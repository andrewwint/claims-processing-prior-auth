"""Record why each routed trial was routed.

Nothing is re-run. For each such trial, the run's recommendation record is read
from the evidence bucket; its citations (criterion, document, page, line) are
filled from the trusted chart and re-checked with the same checks module, and the
failures are written to annotations.json, which the report includes.

Usage: python -m evaluation.annotate
"""

import json
import sys
from pathlib import Path

import boto3

from evaluation.report import ANNOTATIONS, load
from infra.names import EVIDENCE_BUCKET_PREFIX
from prior_auth import checks, evidence_store, stores


def cause(recommendation: dict) -> dict:
    case_id = recommendation["case_id"]
    request = stores.request(case_id)
    case_docs = stores.documents(stores.cases()[case_id]["documents"])
    findings = checks.findings_from_citations(recommendation["citations"], case_docs)
    packet = {"packet_id": recommendation["packet_id"], "case_id": case_id, "findings": findings}
    cited = {f["doc_id"] for f in findings if isinstance(f.get("doc_id"), str)}
    chart = {"docs": stores.documents(cited), "index": stores.chart_index()}
    verdict = checks.recompute(packet, request, stores.criteria(request["payer_id"], request["cpt_code"]), chart)
    def exists(c):
        pages = (case_docs.get(c["doc_id"]) or {}).get("pages", [])
        return 1 <= c["page"] <= len(pages) and 1 <= c["line"] <= len(pages[c["page"] - 1])
    citations = [c | {"cited_line_exists": exists(c),
                      "document_pages": len((case_docs.get(c["doc_id"]) or {}).get("pages", []))}
                 for c in recommendation["citations"]]
    return {"recommendation": recommendation["recommendation"], "citations": citations,
            "check_failures": verdict.failures, "gaps": verdict.gaps}


def main() -> int:
    session = boto3.Session(region_name="us-east-1")
    bucket = f"{EVIDENCE_BUCKET_PREFIX}-{session.client('sts').get_caller_identity()['Account']}"
    s3 = session.client("s3")
    notes = {}
    for t in load():
        if t["outcome"] == "routed" and t.get("run_id"):
            rec = evidence_store.get_recommendation(s3, bucket, t["case_id"], t["run_id"])
            notes[t["run_id"]] = cause(rec) if rec else {"check_failures": ["no recommendation record found"]}
    ANNOTATIONS.write_text(json.dumps(notes, indent=2, sort_keys=True) + "\n")
    print(json.dumps(notes, indent=2)[:3000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
