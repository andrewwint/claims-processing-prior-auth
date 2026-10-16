"""Record beats 2 and 3 on the deployed runtime: CLEAN-1 approved, CF-1 routed with its gap.

Each case is submitted by the intake client; the packet the runtime stored is read
back from the evidence bucket (hash and encryption key recorded, not its text).

Usage: python -m scripts.record_beats23
"""

import json
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

import boto3

from prior_auth import checks
from prior_auth.agent.pipeline import session_id_for
from prior_auth.evidence_store import get_packet, packet_key
from scripts import gateway_client as gc
from scripts.intake import intake_token, invoke
from scripts.redact import find_unredacted, known_values, redact

CASES = {"beat2": "SYN-CASE-CLEAN-1", "beat3": "SYN-CASE-CF-1"}


def main() -> int:
    session = boto3.Session(region_name="us-east-1")
    out = gc.outputs()
    runtime = json.loads(Path(".local/runtime.json").read_text())
    bucket = f"prior-auth-evidence-{session.client('sts').get_caller_identity()['Account']}"
    s3 = session.client("s3")
    token = intake_token(out, session)
    record = {"date": date.today().isoformat(), "runtime_arn": runtime["arn"],
              "sha": subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip(),
              "beats": {}}
    for beat, case_id in CASES.items():
        start = time.time()
        result = invoke(case_id, runtime["arn"], token)
        packet = get_packet(s3, bucket, result["packet_id"]) if "packet_id" in result else None
        head = s3.head_object(Bucket=bucket, Key=packet_key(result["packet_id"])) if packet else {}
        record["beats"][beat] = {
            "case_id": case_id, "session_id": session_id_for(case_id), "response": result,
            "seconds": round(time.time() - start, 1),
            "stored_packet": {"key": packet_key(result["packet_id"]), "sha256": checks.packet_hash(packet),
                              "citations": [(f["criterion_id"], f["doc_id"], f["page"], f["line"]) for f in packet["findings"]],
                              "sse": head.get("ServerSideEncryption"), "kms_key": head.get("SSEKMSKeyId"),
                              "object_lock_mode": head.get("ObjectLockMode")} if packet else None,
        }
        print(beat, case_id, "->", result)
    named = {**known_values(out), bucket: "<evidence-bucket>", runtime["arn"]: "<runtime-arn>"}
    text = redact(json.dumps(record, indent=2, default=str), named)
    assert not find_unredacted(text)
    path = Path(f"evidence/{date.today().isoformat()}/beats-2-and-3.json")
    path.write_text(text + "\n")
    print("->", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
