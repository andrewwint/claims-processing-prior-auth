"""The evidence bucket's run-time prefixes, each written by one role (bucket policy):

- packets/<packet_id>.json                     runtime          untrusted claims, read by the approval service
- recommendations/<case_id>/<run_id>.json      runtime          what the agent recommended, write-once
- queue/<case_id>.json                         case-tool Lambda routed cases for the clinician
- decisions/<case_id>/<run_id>.json            reviewer/approval write-once, chained to the recommendation

Every record is stored as canonical JSON, so the stored bytes hash to the record's hash.
"""

import json

from prior_auth.checks import canonical_bytes, canonical_hash


class AlreadyExists(RuntimeError):
    pass


def packet_key(packet_id: str) -> str:
    return f"packets/{packet_id}.json"


def recommendation_key(case_id: str, run_id: str) -> str:
    return f"recommendations/{case_id}/{run_id}.json"


def queue_key(case_id: str) -> str:
    return f"queue/{case_id}.json"


def decision_key(case_id: str, run_id: str) -> str:
    return f"decisions/{case_id}/{run_id}.json"


def _put(s3, bucket: str, key: str, record: dict, write_once: bool = False) -> str:
    kwargs = {"IfNoneMatch": "*"} if write_once else {}
    try:
        s3.put_object(Bucket=bucket, Key=key, Body=canonical_bytes(record), ContentType="application/json", **kwargs)
    except s3.exceptions.ClientError as e:
        if e.response["Error"]["Code"] in ("PreconditionFailed", "ConditionalRequestConflict"):
            raise AlreadyExists(key) from e
        raise
    return canonical_hash(record)


def _get(s3, bucket: str, key: str) -> dict | None:
    try:
        return json.loads(s3.get_object(Bucket=bucket, Key=key)["Body"].read())
    except s3.exceptions.NoSuchKey:
        return None


def put_packet(s3, bucket: str, packet: dict) -> str:
    return _put(s3, bucket, packet_key(packet["packet_id"]), packet)


def get_packet(s3, bucket: str, packet_id: str) -> dict | None:
    return _get(s3, bucket, packet_key(packet_id))


def put_recommendation(s3, bucket: str, record: dict) -> str:
    return _put(s3, bucket, recommendation_key(record["case_id"], record["run_id"]), record, write_once=True)


def get_recommendation(s3, bucket: str, case_id: str, run_id: str) -> dict | None:
    return _get(s3, bucket, recommendation_key(case_id, run_id))


def put_queue_entry(s3, bucket: str, entry: dict) -> str:
    return _put(s3, bucket, queue_key(entry["case_id"]), entry)


def get_queue_entry(s3, bucket: str, case_id: str) -> dict | None:
    return _get(s3, bucket, queue_key(case_id))


def put_decision(s3, bucket: str, record: dict) -> str:
    return _put(s3, bucket, decision_key(record["case_id"], record["run_id"]), record, write_once=True)


def get_decision(s3, bucket: str, case_id: str, run_id: str) -> dict | None:
    return _get(s3, bucket, decision_key(case_id, run_id))


def stored_hash(s3, bucket: str, key: str) -> str | None:
    """Recompute the hash from the stored object's bytes (the verifier's view)."""
    try:
        body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    except s3.exceptions.NoSuchKey:
        return None
    import hashlib
    return hashlib.sha256(body).hexdigest()
