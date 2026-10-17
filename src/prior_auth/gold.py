"""Gold citations for a synthetic case: for each criterion, the first line in the case's documents
that the criterion's evidence rule accepts. The author's reference extraction, used to show what a
packet looks like (G3) and to check the labels against the rules (M2); never used to decide a case."""

import re

from prior_auth import stores


def gold_citations(case_id: str) -> list[dict]:
    case = stores.cases()[case_id]
    request = stores.request(case_id)
    docs = {d: stores.document(d) for d in case["documents"]}
    cites = []
    for crit in stores.criteria(request["payer_id"], request["cpt_code"]):
        rule = crit["evidence_rule"]
        for doc_id, doc in docs.items():
            if doc and doc["kind"] in rule["doc_kinds"]:
                hit = next((n for n, line in enumerate(doc["pages"][0], start=1) if re.search(rule["pattern"], line)), None)
                if hit:
                    cites.append({"criterion_id": crit["id"], "doc_id": doc_id, "page": 1, "line": hit})
                    break
    return cites


def checklist(case_id: str) -> list[dict]:
    """The packet as the clinician sees it: criterion, evidence, source and status, from gold citations
    run through the real checks and decide()."""
    from prior_auth import checks
    from prior_auth.decide import decide
    case, request = stores.cases()[case_id], stores.request(case_id)
    docs = stores.documents(case["documents"])
    criteria = stores.criteria(request["payer_id"], request["cpt_code"])
    packet = {"packet_id": f"PKT-{case_id}", "case_id": case_id,
              "findings": checks.findings_from_citations(gold_citations(case_id), docs)}
    decision = decide(packet, request, criteria, {"docs": stores.documents({f["doc_id"] for f in packet["findings"]}),
                                                  "index": stores.chart_index()})
    gaps = set(getattr(decision, "gaps", []) or [])
    findings = {f["criterion_id"]: f for f in packet["findings"]}
    rows = []
    for c in criteria:
        f = findings.get(c["id"])
        met = f is not None and c["id"] not in gaps
        rows.append({"criterion": c["id"], "requirement": c["text"], "status": "Met" if met else "Not found",
                     "evidence": f["value"] if met else "",
                     "source": f"{f['doc_id']} p{f['page']} l{f['line']}" if met else ""})
    return rows
