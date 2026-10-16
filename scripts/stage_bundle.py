"""Stage the Lambda bundle: the prior_auth package plus the trusted, read-only
synthetic stores (compiled criteria, charts, chart index, eligibility, cases).

The stores are committed data built by the operator; nothing at run time can
write them. Output: build/lambda/ (git-ignored). Run before synth or deploy.
"""

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "build" / "lambda"
STORES = {
    "policies": ROOT / "data" / "policies" / "compiled",
    "charts": ROOT / "data" / "charts",
    "cases": ROOT / "data" / "cases",
}


def stage(out: Path = OUT) -> Path:
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(ROOT / "src" / "prior_auth", out / "prior_auth",
                    ignore=shutil.ignore_patterns("__pycache__", ".*"))
    trusted = out / "prior_auth" / "trusted"
    for name, src in STORES.items():
        shutil.copytree(src, trusted / name, ignore=shutil.ignore_patterns("*.py", "__pycache__", ".*"))
    return out


def main() -> int:
    print(f"staged {stage().relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
