"""Pre-deploy check for beat 2 (PM, 2026-10-16): the Strands agent with real Nova Pro,
run locally against the live agent gateway, on all six synthetic cases.

Gathering calls go through the deployed gateway as the agent identity (Cedar
enforced). The two ending tools run locally, because the deployed approval
service does not yet have the packet store. Expected: both clean cases approved;
the two counterfactuals, the wrong-patient case and the forged case routed.
"""

import json
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

import boto3
from strands.tools.mcp import MCPClient

from prior_auth import stores
from prior_auth.agent.pipeline import run_case
from prior_auth.agent.strands_agent import DEFAULT_MODEL, gathering_tools, make_call, make_extract
from prior_auth.decide import APPROVAL_ACTION, ROUTE_ACTION
from prior_auth.handlers import approval
from scripts import gateway_client as gc
from scripts.redact import find_unredacted, known_values, redact

EXPECTED = {"approve": "approved", "needs review": "routed"}


def main() -> int:
    session = boto3.Session(region_name="us-east-1")
    out = gc.outputs()
    client = MCPClient(url=out["AgentGatewayUrl"], headers={"Authorization": f"Bearer {gc.agent_token(out, session)}"})
    rows = []
    with client:
        given = sorted(t.tool_name for t in gathering_tools(client.list_tools_sync()))
        live, packets = make_call(client), {}

        def call(action, args):
            if action == APPROVAL_ACTION:
                failures, case_id = approval.review_stored(args["packet_id"], args["packet_hash"], packets.get)
                return {"approved": not failures, "reasons": failures, "case_id": case_id}
            if action == ROUTE_ACTION:
                return {"routed": True}
            return live(action, args)

        extract = make_extract(client)
        for case_id, case in stores.cases().items():
            start = time.time()
            result = run_case(case_id, call, extract, lambda p: packets.__setitem__(p["packet_id"], p),
                              model_id=DEFAULT_MODEL)
            rows.append({
                "case_id": case_id, "label": case["label"], "expected": EXPECTED[case["label"]],
                "outcome": result["outcome"], "reason": result.get("reason"), "gaps": result.get("gaps"),
                "citations": [(f["criterion_id"], f["doc_id"], f["page"], f["line"])
                              for f in result.get("packet", {}).get("findings", [])],
                "seconds": round(time.time() - start, 1),
                "pass": result["outcome"] == EXPECTED[case["label"]],
            })
            print(f"{case_id:24} {case['label']:12} -> {result['outcome']:15} {rows[-1]['pass']} "
                  f"{result.get('reason') or ''} {result.get('gaps') or ''}")
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    record = {"model": DEFAULT_MODEL, "tools_given": given, "sha": sha, "date": date.today().isoformat(),
              "all_pass": all(r["pass"] for r in rows), "cases": rows}
    text = redact(json.dumps(record, indent=2, default=str), known_values(out))
    assert not find_unredacted(text)
    path = Path(f"evidence/{date.today().isoformat()}/beat2-predeploy-check.json")
    path.write_text(text + "\n")
    print("all pass:", record["all_pass"], "->", path)
    return 0 if record["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
