"""Record the demo video with Playwright: a scripted run, captioned, no voice-over (V1).

The demo beats are run first, through `make demo BEAT=<n>` (identifiers masked), and their output
is shown on a terminal-styled page. The workbench beat is driven live: the clinician signs in
through the Cognito hosted UI, opens the fresh counterfactual case, is refused a denial without
a reason, and records one with a reason. Playwright records the page only, never the address bar.

The clinician's password is read from the PA_VIDEO_PASSWORD environment variable (set it with
`read -s`); it is typed into the masked password field and passed to the demo beats so they do
not reset it. It is never printed, logged or saved. The video is written outside the repository.

Usage:
    read -s PA_VIDEO_PASSWORD && export PA_VIDEO_PASSWORD
    python -m scripts.record_video <output-dir outside the repo>
"""

import html
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
USERNAME = "syn-clinician-1"
CASE = "SYN-CASE-CF-1"
WORKBENCH = "http://localhost:8765/"
# 16:9 layout; each still is captured at 8/3 pixel density, so it is exactly 3840x2160 (4K).
VIEWPORT = {"width": 1440, "height": 810}
SCALE = 8 / 3
FRAME = (3840, 2160)
DENIAL_REASON = ("Criterion C3 not met: no functional assessment (Oswestry Disability Index) is documented "
                 "in the submitted chart. Resubmit with the functional assessment.")

# The PM-approved captions, word for word, and how long each is held (seconds).
CAPTIONS = {
    "title": ("Build the Case, Let the Clinician Decide. A prior authorization agent on Amazon Bedrock "
              "AgentCore. Synthetic data. Scripted run recorded with Playwright.", 4),
    "beat1": ("Two gateways. The agent's has five tools, and none of them can deny. The denial tool lives "
              "only on the reviewer gateway, for clinicians.", 7),
    "beat2": ("Case 1: the clean case. The agent cites a chart line for each criterion. Code verifies every "
              "citation and decides. Approved, and re-checked by the approval service before it was recorded.", 8),
    "beat3": ("Case 2: the same case with one note removed. Criterion C3 has no evidence, so the case goes to a "
              "clinician with the gap marked. The agent denies nothing.", 8),
    "beat4": ("The agent tries the denial tool anyway. The reviewer gateway refuses its token, and a Cedar "
              "policy forbids the action for the agent even if it got past.", 8),
    "signin": ("The clinician signs in as a separate identity, with the clinician role.", 5),
    "packet": ("The case the agent built: C1 and C2 met, each with its exact chart line and source. C3 not "
               "found. The model's summary is labeled and used for no decision.", 8),
    "empty": ("A denial needs a specific reason.", 5),
    "denied": ("Denied by the clinician. Recorded with the reviewer's identity and a hash linking it to the "
               "agent's recommendation. This is the only way a denial happens here.", 8),
    "beat6": ("Telemetry holds no chart text: a canary planted in the chart is caught by the scan, and the "
              "real runs came back clean.", 7),
    "close": ("The agent approves only what is clearly covered. Everything else goes to a person. "
              "Code: github.com/andrewwint/claims-processing-prior-auth", 5),
}

BANNER_JS = """
(text) => {
  let b = document.getElementById('pa-caption');
  if (!b) {
    b = document.createElement('div');
    b.id = 'pa-caption';
    b.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:2147483647;background:#111827;color:#fff;' +
      'font:600 22px/1.45 system-ui,sans-serif;padding:16px 28px;box-shadow:0 2px 8px rgba(0,0,0,.3)';
    document.documentElement.appendChild(b);
  }
  b.textContent = text;
  // Keep the page's own content below the banner, so it never covers the packet table.
  document.body.style.paddingTop = (b.offsetHeight + 16) + 'px';
}
"""


def run_beat(beat: int, env: dict) -> str:
    """One demo beat through make (masked by default); returns its output."""
    out = subprocess.run(["make", "-s", "demo", f"BEAT={beat}"], cwd=ROOT, env=env, capture_output=True, text=True)
    text = (out.stdout + out.stderr).strip()
    if out.returncode != 0:
        raise RuntimeError(f"make demo BEAT={beat} failed (exit {out.returncode})")
    return text


def terminal_page(command: str, output: str) -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
    body {{ margin:0; background:#0b1020; color:#e5e7eb; font:18px/1.55 ui-monospace,Menlo,monospace; }}
    .term {{ margin:24px 40px; padding:20px 24px; background:#111827; border-radius:10px; white-space:pre-wrap; }}
    .cmd {{ color:#93c5fd; }}
    </style></head><body><div class="term"><span class="cmd">$ {html.escape(command)}</span>
{html.escape(output)}</div></body></html>"""


def card_page(text: str) -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
    body {{ margin:0; background:#0b1020; color:#f9fafb; font:600 38px/1.4 system-ui,sans-serif;
           display:flex; align-items:center; justify-content:center; height:100vh; text-align:center; }}
    div {{ max-width:900px; padding:0 40px; }}
    </style></head><body><div>{html.escape(text)}</div></body></html>"""


class PacketViewMismatch(RuntimeError):
    pass


def check_packet_view(page_html: str, run_id: str | None) -> None:
    """Fail the recording unless the packet view shows what the caption says: this run, C1 and C2
    Met with their evidence, C3 Not found."""
    problems = []
    if "The stored packet is not the one" in page_html or "No evidence record for this run" in page_html:
        problems.append("the page shows no evidence for this run")
    if run_id and run_id not in page_html:
        problems.append("the page is not showing the fresh run")
    for criterion, status in (("C1", "Met"), ("C2", "Met"), ("C3", "Not found")):
        if not re.search(rf"<td>{criterion}</td><td class=\"{status.split()[0]}\">{status}</td>", page_html):
            problems.append(f"{criterion} is not shown as {status}")
    if problems:
        raise PacketViewMismatch("packet view does not match the caption: " + "; ".join(problems))


class Stills:
    """The video as a list of (still, seconds). Playwright's screen recorder captures at a low,
    fixed bitrate and the window's own size; full-density screenshots stay sharp."""

    def __init__(self, folder: Path):
        self.folder, self.shots = folder, []
        folder.mkdir(parents=True, exist_ok=True)
        for old in folder.glob("s*.png"):
            old.unlink()

    def take(self, page, seconds: float) -> None:
        path = self.folder / f"s{len(self.shots):03d}.png"
        page.screenshot(path=str(path))
        self.shots.append((path, seconds))

    def encode(self, mp4_4k: Path, mp4_1080: Path) -> None:
        listing = self.folder / "stills.txt"
        lines = [f"file '{p.name}'\nduration {d}" for p, d in self.shots]
        lines.append(f"file '{self.shots[-1][0].name}'")  # the concat demuxer needs the last file repeated
        listing.write_text("\n".join(lines) + "\n")
        base = ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing)]
        enc = ["-r", "30", "-c:v", "libx264", "-preset", "slow", "-tune", "stillimage", "-pix_fmt", "yuv420p",
               "-movflags", "+faststart"]
        subprocess.run(base + ["-vf", f"scale={FRAME[0]}:{FRAME[1]}:flags=lanczos", *enc, "-crf", "16",
                               str(mp4_4k)], check=True)
        subprocess.run(base + ["-vf", "scale=1920:1080:flags=lanczos", *enc, "-crf", "18", str(mp4_1080)],
                       check=True)


def caption(page, stills: Stills, key: str) -> None:
    text, hold = CAPTIONS[key]
    page.evaluate(BANNER_JS, text)
    stills.take(page, hold)


def show_terminal(page, stills: Stills, key: str, beat: int, output: str) -> None:
    page.set_content(terminal_page(f"make demo BEAT={beat}", output))
    caption(page, stills, key)


def wait_for_workbench(timeout: float = 20) -> None:
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(WORKBENCH, timeout=2)
            return
        except OSError:
            time.sleep(0.5)
    raise RuntimeError("the workbench did not start on 127.0.0.1:8765")


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    out_dir = Path(sys.argv[1]).expanduser().resolve()
    if ROOT == out_dir or ROOT in out_dir.parents:
        print("refusing: the video must be written outside the repository", file=sys.stderr)
        return 2
    password = os.environ.get("PA_VIDEO_PASSWORD")
    if not password:
        print("refusing: set PA_VIDEO_PASSWORD with `read -s` first", file=sys.stderr)
        return 2
    import socket
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", 8765)) == 0:
            print("refusing: something is already listening on 127.0.0.1:8765; stop any running workbench "
                  "first, so the video drives this checkout's code", file=sys.stderr)
            return 2
    out_dir.mkdir(parents=True, exist_ok=True)
    # The demo beats sign the clinician in by SRP; with the password in this variable they use it
    # instead of resetting it (scripts/gateway_client.password_env).
    env = {**os.environ, "SYN_CLINICIAN_1_PASSWORD": password,
           "PLAYWRIGHT_BROWSERS_PATH": str(ROOT / "build" / "playwright")}
    print("running the demo beats (identifiers masked)...")
    # Beat 3 (the fresh counterfactual run) goes last, immediately before the workbench opens it.
    outputs = {b: run_beat(b, env) for b in (1, 2, 4, 6, 3)}
    run_id = (re.search(r"run (\S+)", outputs[3]) or [None, None])[1]
    print(f"counterfactual run: {run_id}")

    workbench = subprocess.Popen([sys.executable, "-m", "scripts.workbench"], cwd=ROOT, env=env,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_for_workbench()
        if workbench.poll() is not None:
            raise RuntimeError("the workbench exited; the port may be taken")
        from playwright.sync_api import sync_playwright
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = env["PLAYWRIGHT_BROWSERS_PATH"]
        stills = Stills(out_dir / "stills")
        with sync_playwright() as p:
            browser = p.chromium.launch()
            context = browser.new_context(viewport=VIEWPORT, device_scale_factor=SCALE)
            page = context.new_page()
            page.set_content(card_page(CAPTIONS["title"][0]))
            stills.take(page, CAPTIONS["title"][1])
            show_terminal(page, stills, "beat1", 1, outputs[1])
            show_terminal(page, stills, "beat2", 2, outputs[2])
            show_terminal(page, stills, "beat3", 3, outputs[3])
            show_terminal(page, stills, "beat4", 4, outputs[4])

            page.goto(WORKBENCH)
            page.get_by_role("link", name="Sign in").click()
            page.wait_for_load_state("networkidle")
            page.evaluate(BANNER_JS, CAPTIONS["signin"][0])
            page.locator("input[name=username]:visible").first.fill(USERNAME)
            stills.take(page, 1.5)
            page.locator("input[name=password]:visible").first.fill(password)
            stills.take(page, 2)
            page.locator("input[name=signInSubmitButton]:visible, button[type=submit]:visible").first.click()
            page.wait_for_url(WORKBENCH + "**")
            caption(page, stills, "signin")

            page.get_by_role("link", name=CASE).click()
            page.wait_for_load_state("networkidle")
            check_packet_view(page.content(), run_id)
            caption(page, stills, "packet")
            page.get_by_role("button", name="Deny").click()
            page.wait_for_load_state("networkidle")
            caption(page, stills, "empty")
            page.locator("textarea[name=reason]").fill(DENIAL_REASON)
            stills.take(page, 3)
            page.get_by_role("button", name="Deny").click()
            page.wait_for_load_state("networkidle")
            caption(page, stills, "denied")

            show_terminal(page, stills, "beat6", 6, outputs[6])
            page.set_content(card_page(CAPTIONS["close"][0]))
            stills.take(page, CAPTIONS["close"][1])
            context.close()
            browser.close()
    finally:
        workbench.terminate()
    mp4 = out_dir / "prior-auth-demo-4k.mp4"
    stills.encode(mp4, out_dir / "prior-auth-demo-1080p.mp4")
    (out_dir / "run.json").write_text(json.dumps({"case_id": CASE, "run_id": run_id}, indent=2) + "\n")
    print(f"video: {mp4}\ncounterfactual run for verify-chain: {run_id}")
    print("next: python -m scripts.scan_video " + str(mp4))
    return 0


if __name__ == "__main__":
    sys.exit(main())
