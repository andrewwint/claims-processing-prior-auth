"""Build the AgentCore Runtime CodeZip directory: ARM64 (aarch64) wheels for the
runtime extra, plus the prior_auth package with its trusted stores.

Output: build/runtime/ (git-ignored). Uses uv to cross-install manylinux aarch64 wheels.
"""

import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

from scripts.stage_bundle import stage

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "build" / "runtime"
PYTHON = "3.13"


def runtime_requirements() -> list[str]:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    return project["optional-dependencies"]["runtime"]


def build(out: Path = OUT) -> Path:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    subprocess.run(["uv", "pip", "install", "-q", "--python-platform", "aarch64-manylinux2014",
                    "--python-version", PYTHON, "--only-binary", ":all:", "--target", str(out),
                    *runtime_requirements()], check=True)
    staged = stage(ROOT / "build" / "runtime-stage")
    shutil.copytree(staged / "prior_auth", out / "prior_auth")
    shutil.rmtree(staged)
    (out / "main.py").write_text("from prior_auth.agent.runtime_app import app\n\nif __name__ == \"__main__\":\n    app.run()\n")
    return out


def main() -> int:
    out = build()
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file()) / 1_048_576
    print(f"built {out.relative_to(ROOT)} ({size:.0f} MB unzipped)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
