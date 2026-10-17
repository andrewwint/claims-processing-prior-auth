"""A4 and A5 from the recorded runtime configuration: no secret-like value in the runtime's
environment, separate app clients, only the intake client admitted, no Memory used, and the
runtime role's explicit Memory deny."""

import json
from pathlib import Path

from scripts.redact import ACCESS_KEY, CLIENT_SECRET, JWT

RECORD = json.loads((Path(__file__).resolve().parent.parent
                     / "evidence/2026-10-16/runtime-identity-and-memory.json").read_text())
SECRET_NAMES = ("SECRET", "PASSWORD", "TOKEN", "API_KEY", "PRIVATE")


def test_no_secret_like_value_in_the_runtime_environment():
    env = RECORD["runtime"]["environment"]
    assert env and not any(n in k.upper() for k in env for n in SECRET_NAMES)
    for value in env.values():
        assert not (CLIENT_SECRET.search(value) or JWT.search(value) or ACCESS_KEY.search(value)), value


def test_agent_and_clinician_are_separate_clients_and_only_intake_invokes_the_runtime():
    clients = RECORD["app_clients"]
    assert len({clients["agent"], clients["clinician"], clients["intake"]}) == 3
    assert RECORD["runtime"]["authorizer_allowed_clients"] == [clients["intake"]]


def test_no_memory_is_used_and_the_runtime_role_denies_it():
    assert RECORD["agentcore_memories_in_account"] == [] and RECORD["runtime"]["has_memory_configuration"] is False
    denied = {a for d in RECORD["runtime_role_memory_denies"] for a in d["actions"]}
    assert {"bedrock-agentcore:CreateMemory", "bedrock-agentcore:CreateEvent",
            "bedrock-agentcore:RetrieveMemoryRecords"} <= denied
