"""Beat 5 records: queue entry, recommendation, and write-once decision records chained by hash.

An in-memory S3 stands in for the evidence bucket; the handlers are the real ones.
"""

import hashlib
import json
import types

import pytest
from botocore.exceptions import ClientError

from prior_auth import evidence_store, records
from prior_auth.handlers import agent_tools, approval_service, reviewer_tools

BUCKET = "evidence-test"


class NoSuchKey(ClientError):
    pass


class FakeS3:
    def __init__(self):
        self.objects = {}
        self.exceptions = types.SimpleNamespace(ClientError=ClientError, NoSuchKey=NoSuchKey)

    def put_object(self, Bucket, Key, Body, ContentType=None, IfNoneMatch=None):
        if IfNoneMatch == "*" and Key in self.objects:
            raise ClientError({"Error": {"Code": "PreconditionFailed"}}, "PutObject")
        self.objects[Key] = Body

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise NoSuchKey({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        return {"Body": types.SimpleNamespace(read=lambda: self.objects[Key])}


@pytest.fixture
def s3(monkeypatch):
    monkeypatch.setenv("EVIDENCE_BUCKET", BUCKET)
    return FakeS3()


def recommend(s3, case_id="CF-1", run_id="RUN-1"):
    packet = {"packet_id": f"PKT-{case_id}", "case_id": case_id, "run_id": run_id, "findings": []}
    record = records.recommendation_record(case_id=case_id, run_id=run_id, packet=packet,
                                           decision={"decision": "route"}, policy_version=None,
                                           received_at=records.now(), recommended_at=records.now())
    return evidence_store.put_recommendation(s3, BUCKET, record)


def test_stored_bytes_hash_to_the_record_hash(s3):
    rec_hash = recommend(s3)
    key = evidence_store.recommendation_key("CF-1", "RUN-1")
    assert evidence_store.stored_hash(s3, BUCKET, key) == rec_hash
    assert hashlib.sha256(s3.objects[key]).hexdigest() == rec_hash


def test_recommendation_is_write_once(s3):
    recommend(s3)
    with pytest.raises(evidence_store.AlreadyExists):
        recommend(s3)


def test_route_writes_the_queue_entry_with_run_id(s3):
    out = agent_tools.route_to_reviewer({"case_id": "CF-1", "run_id": "RUN-1", "reason": "gap", "gaps": ["C3"]}, s3)
    assert out["routed"] and out["run_id"] == "RUN-1"
    entry = evidence_store.get_queue_entry(s3, BUCKET, "CF-1")
    assert entry["run_id"] == "RUN-1" and entry["gaps"] == ["C3"]


def test_clinician_decision_chains_to_the_recommendation(s3):
    rec_hash = recommend(s3)
    agent_tools.route_to_reviewer({"case_id": "CF-1", "run_id": "RUN-1", "reason": "gap", "gaps": ["C3"]}, s3)
    out = reviewer_tools.record_adverse_determination(
        {"case_id": "CF-1", "reason": "Criterion C3 not documented.", "reviewer": "clinician-1"}, s3)
    assert out["recorded"] and out["recommendation_record_hash"] == rec_hash
    decision = evidence_store.get_decision(s3, BUCKET, "CF-1", "RUN-1")
    assert decision["recommendation_record_hash"] == rec_hash
    assert decision["recommendation_key"] == evidence_store.recommendation_key("CF-1", "RUN-1")
    assert decision["reviewer_identity_source"] == "clinician-app"
    assert evidence_store.stored_hash(s3, BUCKET, evidence_store.decision_key("CF-1", "RUN-1")) == \
        out["decision_record_hash"]


def test_a_run_has_one_decision(s3):
    recommend(s3)
    agent_tools.route_to_reviewer({"case_id": "CF-1", "run_id": "RUN-1", "reason": "gap", "gaps": []}, s3)
    assert reviewer_tools.record_clinician_approval({"case_id": "CF-1", "reviewer": "c"}, s3)["recorded"]
    second = reviewer_tools.record_adverse_determination({"case_id": "CF-1", "reason": "r", "reviewer": "c"}, s3)
    assert not second["recorded"] and "already has a decision" in second["reasons"][0]


def test_decision_refused_without_queue_entry_or_recommendation(s3):
    out = reviewer_tools.record_clinician_approval({"case_id": "CF-9", "reviewer": "c"}, s3)
    assert not out["recorded"] and "not in the review queue" in out["reasons"][0]
    agent_tools.route_to_reviewer({"case_id": "CF-9", "run_id": "RUN-X", "reason": "r", "gaps": []}, s3)
    out = reviewer_tools.record_clinician_approval({"case_id": "CF-9", "reviewer": "c"}, s3)
    assert not out["recorded"] and "no recommendation record" in out["reasons"][0]


def test_denial_still_requires_a_reason(s3):
    out = reviewer_tools.record_adverse_determination({"case_id": "CF-1", "reason": "  "}, s3)
    assert not out["recorded"]


def test_auto_approval_writes_a_chained_decision(s3):
    rec_hash = recommend(s3, "CLEAN-1", "RUN-A")
    packet = {"packet_id": "PKT-CLEAN-1", "case_id": "CLEAN-1", "run_id": "RUN-A", "findings": []}
    evidence_store.put_packet(s3, BUCKET, packet)
    failures, chain = approval_service._record_auto_approval("PKT-CLEAN-1", "CLEAN-1", s3)
    assert failures == [] and chain["recommendation_record_hash"] == rec_hash
    decision = evidence_store.get_decision(s3, BUCKET, "CLEAN-1", "RUN-A")
    assert decision["decision"] == "auto_approval" and decision["reviewer_identity_source"] == "service"
    again, _ = approval_service._record_auto_approval("PKT-CLEAN-1", "CLEAN-1", s3)
    assert again == ["this run already has a decision"]


# L6: verify_chain recomputes every link; a broken link fails verification.
class FakeLogs:
    def __init__(self, spans):
        self.spans = spans

    def describe_log_groups(self, logGroupNamePrefix):
        return {"logGroups": [{"logGroupName": logGroupNamePrefix + "-DEFAULT"}]}

    def get_paginator(self, name):
        spans = self.spans
        return types.SimpleNamespace(paginate=lambda **kw: [{"events": [
            {"message": json.dumps(s)} for s in spans if kw["filterPattern"].strip('"') in json.dumps(s)]}])


class FakeSession:
    def __init__(self, s3, logs):
        self.clients = {"s3": s3, "logs": logs,
                        "sts": types.SimpleNamespace(get_caller_identity=lambda: {"Account": "000000000000"})}

    def client(self, name):
        return self.clients[name]


def chained(s3, monkeypatch):
    from scripts import verify_chain
    monkeypatch.setattr(verify_chain, "EVIDENCE_BUCKET_PREFIX", "evidence")
    monkeypatch.setenv("EVIDENCE_BUCKET", "evidence-000000000000")

    rec_hash = evidence_store.put_recommendation(s3, "evidence-000000000000", records.recommendation_record(
        case_id="CF-1", run_id="RUN-1", packet={"packet_id": "PKT-CF-1", "findings": []},
        decision={"decision": "route"}, policy_version=None, received_at="t", recommended_at="t"))
    agent_tools.route_to_reviewer({"case_id": "CF-1", "run_id": "RUN-1", "reason": "r", "gaps": []}, s3)
    reviewer_tools.record_clinician_approval({"case_id": "CF-1", "reviewer": "c"}, s3)
    span = {"traceId": "T", "spanId": "S", "name": "POST /invocations",
            "attributes": {"pa.recommendation_record_sha256": rec_hash, "pa.run_id": "RUN-1"}}
    return verify_chain, span


def test_verify_chain_passes_for_an_intact_chain(s3, monkeypatch):
    verify_chain, span = chained(s3, monkeypatch)
    assert verify_chain.verify(FakeSession(s3, FakeLogs([span])), "CF-1", "RUN-1")["verified"]


def test_verify_chain_fails_when_the_recommendation_bytes_change(s3, monkeypatch):
    verify_chain, span = chained(s3, monkeypatch)
    key = evidence_store.recommendation_key("CF-1", "RUN-1")
    s3.objects[key] = s3.objects[key].replace(b'"route"', b'"approve"')
    result = verify_chain.verify(FakeSession(s3, FakeLogs([span])), "CF-1", "RUN-1")
    assert not result["verified"] and not result["checks"]["recommendation_hash_matches_stored_bytes"]


def test_verify_chain_fails_without_the_span(s3, monkeypatch):
    verify_chain, _ = chained(s3, monkeypatch)
    result = verify_chain.verify(FakeSession(s3, FakeLogs([])), "CF-1", "RUN-1")
    assert not result["verified"] and not result["checks"]["span_carries_recommendation_hash"]
