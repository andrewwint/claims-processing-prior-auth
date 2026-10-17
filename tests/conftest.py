"""Stage the Lambda bundle (build/lambda, git-ignored) once per test run, so the CDK stack tests
pass on a fresh clone exactly as they do after a deploy."""

import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session", autouse=True)
def lambda_bundle():
    from scripts.stage_bundle import stage
    cwd = os.getcwd()
    os.chdir(ROOT)  # the stacks resolve build/lambda relative to the repository root
    try:
        stage()
        yield
    finally:
        os.chdir(cwd)
