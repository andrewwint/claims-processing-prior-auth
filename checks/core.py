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
NEGATORS = ("no", "not", "without", "denies", "denied", "negative for", "absence of", "absent", "never", "ruled out")
NEGATION_WINDOW_WORDS = 4
NUMBER_WORDS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
    "sixteen seventeen eighteen nineteen twenty".split())}
FINDING_FIELDS = {"criterion_id": str, "doc_id": str, "page": int, "line": int, "value": str}


def packet_hash(packet: dict) -> str:
    canonical = json.dumps(packet, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


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


def source_match(finding: dict, docs: dict) -> str | None:
    """Check 2. Exact NFC substring of the cited line. Returns a failure or None."""
    value = finding["value"]
    if len("".join(value.split())) < MIN_VALUE_CHARS:
        return f"source match: value for {finding['criterion_id']} is shorter than {MIN_VALUE_CHARS} characters"
    line = _cited_line(finding, docs)
    if line is None:
        return f"source match: {finding['doc_id']} page {finding['page']} line {finding['line']} does not exist"
    if _nfc(value) not in _nfc(line):
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

    The quote must come from an allowed kind of document, match the criterion's
    pattern (with any numeric minimums), and not be negated on its line.
    Returns a failure or None. Run only after source_match has passed.
    """
    rule = criterion.get("evidence_rule")
    cid = criterion["id"]
    if not rule:
        return f"evidence rule: {cid} has no compiled evidence rule"
    doc = docs[finding["doc_id"]]
    if doc.get("kind") not in rule["doc_kinds"]:
        return f"evidence rule: {cid} cannot be supported by a {doc.get('kind', 'unknown')} document"
    value = _nfc(finding["value"])
    match = re.search(rule["pattern"], value)
    if match is None:
        return f"evidence rule: value for {cid} does not state what the criterion requires"
    for group, minimum in rule.get("minimums", {}).items():
        n = _number(match.group(group))
        if n is None or n < minimum:
            return f"evidence rule: value for {cid} is below the required {group} of {minimum}"
    line = _nfc(_cited_line(finding, docs))
    before = line[: line.index(value)].lower().split()[-NEGATION_WINDOW_WORDS:]
    window = " ".join(before)
    if any(re.search(rf"\b{re.escape(n)}\b", window) for n in NEGATORS):
        return f"evidence rule: value for {cid} is negated on its line"
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
