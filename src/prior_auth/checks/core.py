"""Checks behind every approval.

The packet is a claim to be checked. A verdict is derived only from trusted
sources: the request record (payer, CPT, patient), the compiled criteria for
that (payer, CPT), and the chart store with its index. Status labels and
patient IDs inside the packet are never read.
"""

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field

MIN_VALUE_CHARS = 4
# Any of these anywhere on the cited line disqualifies it. The list errs strict:
# a line that merely mentions a plan, a goal, a history or a doubt routes to a
# reviewer instead of supporting a criterion.
DISQUALIFYING_TERMS = (
    "no", "not", "none", "nor", "without", "denies", "denied", "negative", "absence", "absent", "never",
    "ruled out", "rule out", "r/o", "evaluate for", "evaluation for", "excluded", "exclude", "unlikely",
    "possible", "possibly", "probable", "suspected", "suspect", "questionable", "query", "history of",
    "plan", "planned", "goal", "goals", "missed", "cancelled", "canceled", "declined", "refused",
    "pending", "recommend", "recommended", "consider", "if", "zero", "resolved", "prior", "previous",
)
NUMBER_WORDS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
    "sixteen seventeen eighteen nineteen twenty".split())}
FINDING_FIELDS = {"criterion_id": str, "doc_id": str, "page": int, "line": int, "value": str}


def canonical_bytes(record) -> bytes:
    """The one canonical JSON encoding: sorted keys, no whitespace, UTF-8."""
    return json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def canonical_hash(record) -> str:
    """The one hash function for packets, recommendation and decision records, the trace and the verifier."""
    return hashlib.sha256(canonical_bytes(record)).hexdigest()


packet_hash = canonical_hash  # packets are records too


def schema_failures(packet, criterion_ids: set[str]) -> list[str]:
    """Check 1. The packet's shape, and findings only for compiled criteria."""
    if not isinstance(packet, dict):
        return ["schema: packet is not an object"]
    failures = []
    if not isinstance(packet.get("case_id"), str) or not packet["case_id"]:
        failures.append("schema: missing case_id")
    findings = packet.get("findings")
    if not isinstance(findings, list):
        return failures + ["schema: findings is not a list"]
    for i, f in enumerate(findings):
        if not isinstance(f, dict):
            failures.append(f"schema: finding {i} is not an object")
            continue
        for name, kind in FINDING_FIELDS.items():
            if type(f.get(name)) is not kind:
                failures.append(f"schema: finding {i} field {name} missing or not {kind.__name__}")
        if isinstance(f.get("criterion_id"), str) and f["criterion_id"] not in criterion_ids:
            failures.append(f"schema: finding {i} cites criterion {f['criterion_id']} not in the compiled policy")
    return failures


def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


CITATION_FIELDS = ("criterion_id", "doc_id", "page", "line")


def findings_from_citations(citations: list[dict], docs: dict) -> list[dict]:
    """Turn the model's citations into findings.

    The model returns citations only: (criterion_id, doc_id, page, line). Each
    finding's value is filled from the trusted chart store, so any value the
    model supplied is ignored. A citation to a line that does not exist keeps an
    empty value, which source match then refuses.
    """
    findings = []
    for c in citations:
        f = {k: c.get(k) for k in CITATION_FIELDS}
        line = _cited_line(f, docs) if all(isinstance(f[k], int) for k in ("page", "line")) else None
        f["value"] = line if line is not None else ""
        findings.append(f)
    return findings


def source_match(finding: dict, docs: dict) -> str | None:
    """Check 2. The value must be exactly the cited line (NFC). Returns a failure or None.

    Values are filled from the chart store by code, so for an honest packet this
    always holds; it still refuses a stored packet whose values were edited.
    """
    value = finding["value"]
    if len("".join(value.split())) < MIN_VALUE_CHARS:
        return f"source match: value for {finding['criterion_id']} is shorter than {MIN_VALUE_CHARS} characters"
    line = _cited_line(finding, docs)
    if line is None:
        return f"source match: {finding['doc_id']} page {finding['page']} line {finding['line']} does not exist"
    if _nfc(value) != _nfc(line):
        return f"source match: value for {finding['criterion_id']} not at {finding['doc_id']} p{finding['page']} l{finding['line']}"
    return None


def _cited_line(finding: dict, docs: dict) -> str | None:
    doc = docs.get(finding["doc_id"])
    try:
        return doc["pages"][finding["page"] - 1][finding["line"] - 1] if finding["page"] > 0 and finding["line"] > 0 else None
    except (TypeError, KeyError, IndexError):
        return None


def _number(text: str) -> int | None:
    return int(text) if text.isdigit() else NUMBER_WORDS.get(text.lower())


def satisfies_rule(finding: dict, criterion: dict, docs: dict) -> str | None:
    """Binds a finding to its criterion, from the compiled criterion's evidence rule.

    The cited line (from the trusted chart) must come from an allowed kind of
    document, contain the criterion's pattern with every numeric minimum met, and
    carry no negating, hedging or planning term anywhere on the line.
    Returns a failure or None. Run only after source_match has passed.
    """
    rule = criterion.get("evidence_rule")
    cid = criterion["id"]
    if not rule:
        return f"evidence rule: {cid} has no compiled evidence rule"
    doc = docs[finding["doc_id"]]
    if doc.get("kind") not in rule["doc_kinds"]:
        return f"evidence rule: {cid} cannot be supported by a {doc.get('kind', 'unknown')} document"
    groups = set(re.compile(rule["pattern"]).groupindex)
    if groups != set(rule.get("minimums", {})):
        return f"evidence rule: {cid} rule must set a minimum for every number it captures"
    # The rule runs on the trusted cited line, never on a packet-supplied value.
    line = _nfc(_cited_line(finding, docs))
    match = re.search(rule["pattern"], line)
    if match is None:
        return f"evidence rule: the line cited for {cid} does not state what the criterion requires"
    for group, minimum in rule.get("minimums", {}).items():
        n = _number(match.group(group))
        if n is None or n < minimum:
            return f"evidence rule: the line cited for {cid} is below the required {group} of {minimum}"
    lowered = line.lower()
    if "n't" in lowered or any(re.search(rf"(?<![a-z]){re.escape(t)}(?![a-z])", lowered) for t in DISQUALIFYING_TERMS):
        return f"evidence rule: the line cited for {cid} negates, hedges or plans rather than states"
    return None


def same_patient(finding: dict, index: dict, patient_id: str) -> str | None:
    """Check 3. The document's owner comes from the chart index, never the packet."""
    owner = index.get(finding["doc_id"])
    if owner is None:
        return f"same patient: {finding['doc_id']} is not in the chart index"
    if owner != patient_id:
        return f"same patient: {finding['doc_id']} belongs to another patient"
    return None


@dataclass
class Verdict:
    statuses: dict[str, str] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)

    @property
    def gaps(self) -> list[str]:
        return [c for c, s in self.statuses.items() if s != "Met"]

    @property
    def approvable(self) -> bool:
        return bool(self.statuses) and not self.failures and not self.gaps


def recompute(packet, request: dict, criteria: list[dict], chart: dict) -> Verdict:
    """Rebuild every criterion's status from trusted sources.

    request: the trusted request record (patient_id, payer_id, cpt_code).
    criteria: the compiled criteria for the request's (payer, CPT).
    chart: {"docs": {doc_id: {"pages": [[line, ...], ...]}}, "index": {doc_id: patient_id}}.
    """
    verdict = Verdict()
    if not criteria:
        verdict.failures.append("no verified policy")
        return verdict
    ids = [c["id"] for c in criteria]
    verdict.failures += schema_failures(packet, set(ids))
    if verdict.failures:
        verdict.statuses = {i: "Not checked" for i in ids}
        return verdict
    if packet["case_id"] != request["case_id"]:
        verdict.failures.append("schema: packet case_id does not match the request")
    by_criterion: dict[str, list[dict]] = {i: [] for i in ids}
    for f in packet["findings"]:
        by_criterion[f["criterion_id"]].append(f)
    # One cited line may support only one criterion.
    used: dict[tuple, str] = {}
    for f in packet["findings"]:
        key = (f["doc_id"], f["page"], f["line"])
        if used.setdefault(key, f["criterion_id"]) != f["criterion_id"]:
            verdict.failures.append(f"evidence rule: {f['doc_id']} p{f['page']} l{f['line']} is cited for more than one criterion")
    by_id = {c["id"]: c for c in criteria}
    for cid in ids:
        findings = by_criterion[cid]
        problems = []
        for f in findings:
            found = [p for p in (same_patient(f, chart["index"], request["patient_id"]), source_match(f, chart["docs"])) if p]
            if not found:
                rule_failure = satisfies_rule(f, by_id[cid], chart["docs"])
                found = [rule_failure] if rule_failure else []
            problems += found
        verdict.failures += problems
        verdict.statuses[cid] = "Met" if findings and not problems else "Not found"
    return verdict
