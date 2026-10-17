"""The Makefile only wraps existing scripts: every module a target runs exists, deploys go
through the guard, there is no teardown target, and no AWS profile or account is named."""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAKEFILE = (ROOT / "Makefile").read_text()
EXPECTED = {"test", "demo", "workbench", "deploy", "smoke", "verify-chain", "report", "scan"}


def targets() -> dict[str, list[str]]:
    out, current = {}, None
    for line in MAKEFILE.splitlines():
        if m := re.match(r"^([a-z-]+):", line):
            current = m.group(1)
            out[current] = []
        elif line.startswith("\t") and current:
            out[current].append(line.strip())
    return out


def test_the_expected_targets_exist_and_teardown_is_not_one():
    t = targets()
    assert EXPECTED <= set(t) and not any("teardown" in name for name in t)
    assert "scripts.teardown" not in "".join(sum(t.values(), []))


def test_every_module_a_target_runs_exists():
    for name, recipe in targets().items():
        for module in re.findall(r"-m ([a-z_.]+)", " ".join(recipe)):
            if module == "pytest":
                continue
            assert (ROOT / (module.replace(".", "/") + ".py")).is_file(), (name, module)


def test_deploy_goes_only_through_the_guard():
    assert any("-m scripts.deploy" in line for line in targets()["deploy"])
    assert "cdk deploy" not in MAKEFILE and "aws-cdk" not in MAKEFILE


def test_no_profile_or_account_is_named():
    assert "AWS_PROFILE=" not in MAKEFILE and not re.search(r"\d{12}", MAKEFILE)


def test_demo_is_redacted_by_default():
    assert "--redact" in " ".join(targets()["demo"])


def test_recipes_run_with_pipefail():
    assert "SHELL := /bin/bash" in MAKEFILE and "-o pipefail" in MAKEFILE


def _make(target: str, py: str) -> int:
    return subprocess.run(["make", "-s", target, f"PY={py}"], cwd=ROOT, capture_output=True).returncode


def test_a_failing_scan_fails_the_target():
    assert _make("scan", "python3 -c 'import sys; sys.exit(1)'") != 0


def test_a_passing_scan_passes_the_target():
    assert _make("scan", "python3 -c 'import sys; sys.exit(0)'") == 0
