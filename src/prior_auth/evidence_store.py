"""The evidence bucket's run-time prefixes: packets (untrusted claims) for now;
queue, recommendations and decisions arrive with evidence-record-and-trace."""

import json

from prior_auth import checks

PACKETS = "packets/"


def packet_key(packet_id: str) -> str:
    return f"{PACKETS}{packet_id}.json"


def put_packet(s3, bucket: str, packet: dict) -> None:
    """Stored as canonical JSON, so the bytes hash to the packet's hash. SSE-KMS comes from the bucket default."""
    body = json.dumps(packet, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    s3.put_object(Bucket=bucket, Key=packet_key(packet["packet_id"]), Body=body, ContentType="application/json")


def get_packet(s3, bucket: str, packet_id: str) -> dict | None:
    try:
        obj = s3.get_object(Bucket=bucket, Key=packet_key(packet_id))
    except s3.exceptions.NoSuchKey:
        return None
    return json.loads(obj["Body"].read())


def stored_hash(s3, bucket: str, packet_id: str) -> str | None:
    packet = get_packet(s3, bucket, packet_id)
    return checks.packet_hash(packet) if packet is not None else None
