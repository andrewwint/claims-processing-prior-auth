"""The clinician workbench (beat 5): one local page, bound to 127.0.0.1:8765.

- Sign-in: Cognito hosted UI, authorization code with PKCE (S256) and `state`,
  handled by Authlib. The callback is the one registered on the clinician client.
- Queue and packets: read with the operator's local AWS credentials, read-only
  (single tenant, demo only; README "Known limitations").
- Decisions: approve, or deny with a required reason, through the reviewer
  gateway under the clinician's own access token. The reviewer Lambda writes the
  decision record chained to the run's recommendation record.

Usage: python -m scripts.workbench   (then open http://localhost:8765/)
"""

import html
import json
import secrets
import sys
import urllib.parse
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import boto3
from authlib.common.security import generate_token
from authlib.integrations.requests_client import OAuth2Session

from infra.identity import WORKBENCH_CALLBACK, WORKBENCH_LOGOUT
from infra.names import EVIDENCE_BUCKET_PREFIX
from prior_auth import evidence_store, stores
from prior_auth.checks import canonical_hash
from prior_auth.handlers.schemas import REVIEWER_TARGET
from scripts import gateway_client as gc

HOST, PORT = "127.0.0.1", 8765
COOKIE = "pa_workbench"
SUMMARY_LABEL = "Model summary — not used for any decision"
DENY_TOOL = f"{REVIEWER_TARGET}___record_adverse_determination"
APPROVE_TOOL = f"{REVIEWER_TARGET}___record_clinician_approval"


# ---------- the packet view (pure, tested) ----------

def criterion_rows(criteria: list[dict], queued: dict, packet: dict | None) -> list[dict]:
    """One row per criterion, with the failure states labeled distinctly (design D4)."""
    reason = queued.get("reason") or ""
    if reason.startswith("extraction failed"):
        stop = reason.split("stop reason", 1)[-1].strip() if "stop reason" in reason else reason
        return [{"id": c["id"], "status": "Extraction failed", "detail": f"stop reason: {stop}"} for c in criteria]
    if reason == "no verified policy":
        return [{"id": c["id"], "status": "No verified policy", "detail": ""} for c in criteria]
    gaps = set(queued.get("gaps") or [])
    findings = {f["criterion_id"]: f for f in (packet or {}).get("findings", [])}
    rows = []
    for c in criteria:
        f = findings.get(c["id"])
        if c["id"] in gaps or f is None or not f.get("value"):
            rows.append({"id": c["id"], "status": "Not found", "detail": c.get("text", "")})
        else:
            rows.append({"id": c["id"], "status": "Met", "detail": f["value"],
                         "source": f"{f['doc_id']}, page {f['page']}, line {f['line']}"})
    return rows


def packet_matches(packet: dict | None, recommendation: dict | None, run_id: str) -> bool:
    """The packet shown must be the one this run recommended (packets are keyed by case)."""
    return bool(packet and recommendation and packet.get("run_id") == run_id
                and canonical_hash(packet) == recommendation.get("packet_hash"))


def tool_result(response: dict) -> dict:
    """The tool's JSON result from an MCP tools/call response, or the refusal."""
    body = response.get("body")
    if not isinstance(body, dict):
        return {"recorded": False, "reasons": [f"HTTP {response.get('http_status')}"]}
    if "error" in body:
        return {"recorded": False, "reasons": [body["error"].get("message", "refused")]}
    result = body.get("result", {})
    if result.get("structuredContent"):
        return result["structuredContent"]
    for item in result.get("content", []):
        if item.get("type") == "text":
            try:
                return json.loads(item["text"])
            except json.JSONDecodeError:
                return {"recorded": False, "reasons": [item["text"]]}
    return {"recorded": False, "reasons": ["empty tool result"]}


# ---------- the server ----------

class Workbench:
    def __init__(self, session: boto3.Session):
        self.out = gc.outputs()
        self.s3 = session.client("s3")
        account = session.client("sts").get_caller_identity()["Account"]
        self.bucket = f"{EVIDENCE_BUCKET_PREFIX}-{account}"
        self.sessions: dict[str, dict] = {}
        domain = self.out["TokenDomain"]
        self.authorize_url, self.token_url = f"{domain}/oauth2/authorize", f"{domain}/oauth2/token"
        self.logout_url = f"{domain}/logout?" + urllib.parse.urlencode(
            {"client_id": self.out["ClinicianClientId"], "logout_uri": WORKBENCH_LOGOUT})

    def oauth(self) -> OAuth2Session:
        return OAuth2Session(self.out["ClinicianClientId"], scope="openid", redirect_uri=WORKBENCH_CALLBACK,
                             code_challenge_method="S256", token_endpoint_auth_method="none")

    def queue(self) -> list[dict]:
        known = stores.cases()
        entries = []
        pages = self.s3.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix="queue/")
        for key in pages.search("Contents[].Key"):
            if not key:
                continue
            entry = evidence_store._get(self.s3, self.bucket, key)
            if not entry or entry.get("case_id") not in known or not entry.get("run_id"):
                continue
            decided = evidence_store.get_decision(self.s3, self.bucket, entry["case_id"], entry["run_id"])
            entries.append(entry | {"decided": decided["decision"] if decided else None})
        return sorted(entries, key=lambda e: e.get("queued_at") or "", reverse=True)

    def case(self, case_id: str) -> dict | None:
        queued = evidence_store.get_queue_entry(self.s3, self.bucket, case_id)
        if not queued or not queued.get("run_id"):
            return None
        run_id = queued["run_id"]
        request = stores.request(case_id) or {}
        criteria = stores.criteria(request.get("payer_id"), request.get("cpt_code")) or []
        recommendation = evidence_store.get_recommendation(self.s3, self.bucket, case_id, run_id)
        packet = evidence_store.get_packet(self.s3, self.bucket, f"PKT-{case_id}")
        matches = packet_matches(packet, recommendation, run_id)
        return {"queued": queued, "request": request, "recommendation": recommendation,
                "packet": packet if matches else None, "packet_matches": matches,
                "rows": criterion_rows(criteria, queued, packet if matches else None),
                "decision": evidence_store.get_decision(self.s3, self.bucket, case_id, run_id)}

    def decide(self, access_token: str, case_id: str, run_id: str, action: str, reason: str, reviewer: str) -> dict:
        """The decision names the run the clinician reviewed; the Lambda refuses it if the queue moved on."""
        if action == "deny":
            name, args = DENY_TOOL, {"case_id": case_id, "run_id": run_id, "reason": reason, "reviewer": reviewer}
        else:
            name, args = APPROVE_TOOL, {"case_id": case_id, "run_id": run_id, "reviewer": reviewer}
        return tool_result(gc.mcp(self.out["ReviewerGatewayUrl"], access_token, "tools/call",
                                  {"name": name, "arguments": args}))


def _page(title: str, body: str) -> bytes:
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{html.escape(title)}</title>
<style>
:root{{--bg:#fff;--fg:#1d1d1f;--muted:#6b6b70;--line:#d9d9de;--ok:#1a7f37;--warn:#9a6700;--bad:#cf222e;--box:#f6f6f8}}
@media (prefers-color-scheme: dark){{:root{{--bg:#151517;--fg:#ececf0;--muted:#a0a0a8;--line:#3a3a40;--ok:#4ac26b;--warn:#d4a72c;--bad:#ff7b72;--box:#1f1f23}}}}
body{{background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif;margin:0 auto;max-width:860px;padding:16px}}
table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}}
.muted{{color:var(--muted)}}.Met{{color:var(--ok)}}.Not{{color:var(--bad)}}.Extraction,.No{{color:var(--warn)}}
.box{{background:var(--box);border:1px solid var(--line);border-radius:6px;padding:10px 12px;margin:12px 0}}
textarea{{width:100%;box-sizing:border-box}}button{{padding:6px 14px;margin-right:8px}}code{{font-size:13px}}
</style></head><body><p class="muted">Synthetic data only. Workbench (demo, single tenant).</p>{body}</body></html>""".encode()


def make_handler(app: Workbench):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # no request lines (they carry the OAuth code)
            pass

        def _session(self) -> tuple[str, dict]:
            jar = cookies.SimpleCookie(self.headers.get("Cookie", ""))
            sid = jar[COOKIE].value if COOKIE in jar else None
            if sid not in app.sessions:
                sid = secrets.token_urlsafe(32)
                app.sessions[sid] = {"csrf": secrets.token_urlsafe(32)}
            return sid, app.sessions[sid]

        def _send(self, status: int, body: bytes = b"", sid: str | None = None, location: str | None = None):
            self.send_response(status)
            if location:
                self.send_header("Location", location)
            if sid:
                # Lax, so the cookie survives the redirect back from the hosted UI.
                self.send_header("Set-Cookie", f"{COOKIE}={sid}; HttpOnly; SameSite=Lax; Path=/")
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            sid, sess = self._session()
            url = urllib.parse.urlsplit(self.path)
            if url.path == "/login":
                verifier = generate_token(48)
                uri, state = app.oauth().create_authorization_url(app.authorize_url, code_verifier=verifier)
                sess.update(verifier=verifier, state=state)
                return self._send(302, sid=sid, location=uri)
            if url.path == "/callback":
                return self._callback(sid, sess, url)
            if url.path == "/logout":
                app.sessions.pop(sid, None)
                return self._send(302, location=app.logout_url)
            if "token" not in sess:
                return self._send(200, _page("Workbench", '<h1>Workbench</h1><p><a href="/login">Sign in</a></p>'),
                                  sid=sid)
            if url.path == "/case":
                case_id = urllib.parse.parse_qs(url.query).get("id", [""])[0]
                return self._send(200, self._case_page(sess, case_id), sid=sid)
            return self._send(200, self._queue_page(sess), sid=sid)

        def do_POST(self):
            sid, sess = self._session()
            length = int(self.headers.get("Content-Length", 0))
            form = urllib.parse.parse_qs(self.rfile.read(length).decode())
            field = lambda k: form.get(k, [""])[0]
            if "token" not in sess or not secrets.compare_digest(field("csrf"), sess["csrf"]):
                return self._send(403, _page("Refused", "<p>Refused: not signed in, or a stale form.</p>"), sid=sid)
            case_id, run_id, action, reason = field("case_id"), field("run_id"), field("action"), field("reason")
            if action == "deny" and not reason.strip():
                result = {"recorded": False, "reasons": ["a specific reason is required"]}
            else:
                result = app.decide(sess["token"]["access_token"], case_id, run_id, action, reason, sess["username"])
            sess["flash"] = result
            return self._send(303, sid=sid, location="/case?" + urllib.parse.urlencode({"id": case_id}))

        def _callback(self, sid, sess, url):
            params = urllib.parse.parse_qs(url.query)
            state = params.get("state", [""])[0]
            expected = sess.pop("state", None)
            verifier = sess.pop("verifier", None)
            if not expected or not secrets.compare_digest(state, expected):
                return self._send(400, _page("Refused", "<p>Sign-in refused: state does not match.</p>"), sid=sid)
            token = app.oauth().fetch_token(app.token_url, authorization_response=WORKBENCH_CALLBACK + "?" + url.query,
                                            code_verifier=verifier, state=expected)
            claims = gc.claims(token["access_token"])
            # The reviewer is named as this app reports it (README: identity validation deferred).
            sess.update(token=token, username=claims.get("username") or claims.get("sub"),
                        role=claims.get("pa_role"), csrf=secrets.token_urlsafe(32))
            return self._send(302, sid=sid, location="/")

        def _header(self, sess) -> str:
            return (f'<p>Signed in as <b>{html.escape(sess["username"] or "")}</b> '
                    f'(role claim: {html.escape(str(sess.get("role")))}) · <a href="/">Queue</a> · '
                    f'<a href="/logout">Sign out</a></p>')

        def _queue_page(self, sess) -> bytes:
            rows = "".join(
                f'<tr><td><a href="/case?{urllib.parse.urlencode({"id": e["case_id"]})}">{html.escape(e["case_id"])}</a></td>'
                f'<td>{html.escape(e.get("reason") or "")}</td><td>{html.escape(", ".join(e.get("gaps") or []))}</td>'
                f'<td>{html.escape(e["decided"] or "awaiting decision")}</td></tr>' for e in app.queue())
            return _page("Workbench queue", self._header(sess) + "<h1>Review queue</h1><table><tr><th>Case</th>"
                         f"<th>Routed because</th><th>Gaps</th><th>Status</th></tr>{rows}</table>")

        def _case_page(self, sess, case_id: str) -> bytes:
            view = app.case(case_id)
            if view is None:
                return _page("Not queued", self._header(sess) + "<p>This case is not in the review queue.</p>")
            q, req = view["queued"], view["request"]
            flash = sess.pop("flash", None)
            note = ""
            if flash:
                ok = flash.get("recorded")
                note = (f'<div class="box"><b>{"Recorded" if ok else "Refused"}</b>: '
                        f'{html.escape(json.dumps(flash, sort_keys=True))}</div>')
            rows = "".join(
                f'<tr><td>{html.escape(r["id"])}</td><td class="{html.escape(r["status"].split()[0])}">'
                f'{html.escape(r["status"])}</td><td>{html.escape(r["detail"])}'
                + (f'<br><span class="muted">{html.escape(r["source"])}</span>' if r.get("source") else "")
                + "</td></tr>" for r in view["rows"])
            summary = ((view["packet"] or {}).get("model_summary") or {}).get("text")
            summary_box = (f'<div class="box"><b>{SUMMARY_LABEL}</b><br>{html.escape(summary)}</div>' if summary
                           else f'<div class="box"><b>{SUMMARY_LABEL}</b><br><span class="muted">none</span></div>')
            mismatch = "" if view["packet_matches"] else (
                '<p class="muted">The stored packet is not the one this run recommended; '
                'criteria are shown from the routing record only.</p>')
            if view["decision"]:
                d = view["decision"]
                action = (f'<div class="box"><b>Decided:</b> {html.escape(d["decision"])} by '
                          f'{html.escape(d["reviewer_identity"])} (as the clinician app reports it) at '
                          f'{html.escape(d["decided_at"])}<br>Recommendation record hash: '
                          f'<code>{html.escape(d["recommendation_record_hash"])}</code></div>')
            else:
                hidden = (f'<input type="hidden" name="csrf" value="{html.escape(sess["csrf"])}">'
                          f'<input type="hidden" name="case_id" value="{html.escape(case_id)}">'
                          f'<input type="hidden" name="run_id" value="{html.escape(q["run_id"])}">')
                action = (f'<form method="post" action="/decide">{hidden}'
                          '<p><label>Reason (required to deny)<br><textarea name="reason" rows="3"></textarea></label></p>'
                          '<button name="action" value="approve">Approve</button>'
                          '<button name="action" value="deny">Deny</button></form>')
            return _page(f"Case {case_id}", self._header(sess) + note
                         + f'<h1>{html.escape(case_id)}</h1><p>CPT {html.escape(str(req.get("cpt_code")))} · '
                         f'payer {html.escape(str(req.get("payer_id")))} · run <code>{html.escape(q["run_id"])}</code></p>'
                         f'<p>Routed because: <b>{html.escape(q.get("reason") or "")}</b></p>{mismatch}'
                         f'<table><tr><th>Criterion</th><th>Status</th><th>Evidence and source</th></tr>{rows}</table>'
                         f'{summary_box}{action}')

    return Handler


def main() -> int:
    app = Workbench(boto3.Session(region_name="us-east-1"))
    server = ThreadingHTTPServer((HOST, PORT), make_handler(app))
    print(f"Workbench on http://localhost:{PORT}/ (bound to {HOST})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
