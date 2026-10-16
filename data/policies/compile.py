"""Compile a synthetic payer policy into verified criteria (G1, G2).

Each criterion keeps its text, the policy version, its exact source location
(file and line), and its evidence rule. The compile step re-reads each
criterion's text at that location and refuses to emit a file if it isn't there.

Usage: python -m data.policies.compile
"""

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "source"
COMPILED = HERE / "compiled"
CRITERION = re.compile(r"^(?P<section>\d+\.\d+) (?P<id>C\d+): (?P<text>.+)$")


class CompileError(ValueError):
    pass


def verify_locations(criteria: list[dict], lines: list[str]) -> None:
    """Each criterion's text must be at its stated source line."""
    for c in criteria:
        n = c["source_location"]["line"]
        if not (1 <= n <= len(lines)) or c["text"] not in lines[n - 1]:
            raise CompileError(f"{c['id']} text not at its stated location")


def compile_policy(path: Path) -> dict:
    lines = path.read_text().splitlines()
    meta = dict(re.match(r"^(Policy version|Payer ID|Policy ID): (.+)$", l).groups()
                for l in lines if re.match(r"^(Policy version|Payer ID|Policy ID): ", l))
    cpt = re.search(r"^Procedure: CPT (\d{5})", path.read_text(), re.M).group(1)
    criteria = []
    for i, line in enumerate(lines):
        m = CRITERION.match(line)
        if not m:
            continue
        if lines[i + 1].strip() != "```rule":
            raise CompileError(f"{m['id']} has no evidence rule")
        end = lines.index("```", i + 2)
        rule = json.loads("\n".join(lines[i + 2:end]))
        groups = set(re.compile(rule["pattern"]).groupindex)
        if groups != set(rule.get("minimums", {})):
            raise CompileError(f"{m['id']} rule captures a number without a minimum")
        criteria.append({"id": m["id"], "text": m["text"], "policy_version": meta["Policy version"],
                         "source_location": {"file": path.name, "line": i + 1, "section": m["section"]},
                         "evidence_rule": rule})
    verify_locations(criteria, lines)
    if not criteria:
        raise CompileError(f"{path.name} has no criteria")
    return {"_label": "SYNTHETIC DATA ONLY. Compiled from a synthetic policy.", "policy_id": meta["Policy ID"],
            "policy_version": meta["Policy version"], "payer_id": meta["Payer ID"], "cpt_code": cpt,
            "criteria": criteria}


def output_path(compiled: dict) -> Path:
    return COMPILED / compiled["payer_id"] / f"{compiled['cpt_code']}.json"


def main() -> int:
    for src in sorted(SOURCE.glob("*.md")):
        compiled = compile_policy(src)
        out = output_path(compiled)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(compiled, indent=2) + "\n")
        print(f"compiled {src.name} -> {out.relative_to(HERE.parent.parent)} ({len(compiled['criteria'])} criteria)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
