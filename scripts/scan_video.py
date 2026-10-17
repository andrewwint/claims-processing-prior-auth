"""Scan a recorded video for identifiers before it is published (V1).

Extracts a frame every 2 seconds with ffmpeg, reads each frame's text with macOS Vision OCR
(ocrmac), and runs the public scan's matcher over it: this deployment's identifiers (from the
local, git-ignored files, plus the Cognito domain host), account IDs, ARNs, emails, tokens and
SSO role names. Frames are written next to the video, outside the repository. A positive
control first: a frame rendered with a planted ARN must be caught. Exit 1 on any hit.

Usage: python -m scripts.scan_video <video.mp4>
"""

import json
import subprocess
import sys
from pathlib import Path

from scripts import public_scan as ps


def frames(video: Path) -> list[Path]:
    out = video.parent / f"{video.stem}-frames"
    out.mkdir(exist_ok=True)
    for old in out.glob("*.png"):
        old.unlink()
    subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(video), "-vf", "fps=0.5", str(out / "f%04d.png")],
                   check=True)
    return sorted(out.glob("*.png"))


def ocr(image: Path) -> str:
    from ocrmac import ocrmac
    return "\n".join(t for t, _, _ in ocrmac.OCR(str(image)).recognize())


def identifiers() -> list[str]:
    exact = ps.known_identifiers()
    outputs = ps.ROOT / ".local" / "d1-outputs.json"
    if outputs.exists():
        domain = json.loads(outputs.read_text())["PriorAuthGateways"].get("TokenDomain", "")
        host = domain.split("//")[-1]
        exact += [host, host.split(".")[0]]
    return sorted({v for v in exact if v and len(v) >= 6})


def positive_control(exact: list[str], scratch: Path) -> bool:
    """Render a frame with a planted ARN and check OCR plus the matcher catch it."""
    from PIL import Image, ImageDraw, ImageFont
    planted = "arn:aws:iam::" + "4040" + "30302020" + ":role/planted"
    img = Image.new("RGB", (1280, 200), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 32)
    except OSError:
        font = ImageFont.load_default()
    draw.text((40, 80), planted, fill="black", font=font)
    path = scratch / "control.png"
    img.save(path)
    caught = ps.scan_text(ocr(path), exact, ps.allowed())
    path.unlink()
    return any(kind in ("arn", "account id") for kind, _, _ in caught)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    video = Path(sys.argv[1]).expanduser().resolve()
    exact = identifiers()
    if not positive_control(exact, video.parent):
        print("FAIL: the positive control was not caught; the OCR scan cannot be trusted")
        return 1
    print(f"positive control caught; scanning for {len(exact)} deployment identifiers and the generic patterns")
    hits = 0
    shots = frames(video)
    for shot in shots:
        for kind, value, _ in ps.scan_text(ocr(shot), exact, ps.allowed()):
            hits += 1
            print(f"HIT {shot.name} ({(int(shot.stem[1:]) - 1) * 2}s) {kind}: {value}")
    print(f"{len(shots)} frames, {hits} hits" if hits else f"PASS: {len(shots)} frames, no identifiers")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
