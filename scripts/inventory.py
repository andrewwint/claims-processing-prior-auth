"""List every resource type this project creates, filtered to project names."""

import boto3

from infra.names import BUDGET_NAMES, BUDGET_STACK, SECRET_PREFIX, is_project_name

LIVE_STACK = {"CREATE_COMPLETE", "UPDATE_COMPLETE", "CREATE_IN_PROGRESS", "UPDATE_IN_PROGRESS",
              "DELETE_FAILED", "ROLLBACK_COMPLETE", "UPDATE_ROLLBACK_COMPLETE", "DELETE_IN_PROGRESS",
              "ROLLBACK_FAILED", "UPDATE_ROLLBACK_FAILED", "CREATE_FAILED"}


def _search(client, op, expr, **kw):
    return list(client.get_paginator(op).paginate(**kw).search(expr))


def inventory(session: boto3.Session) -> dict[str, list[str]]:
    cfn = session.client("cloudformation")
    agentcore = session.client("bedrock-agentcore-control")
    found: dict[str, list[str]] = {}

    found["cloudformation stack"] = [
        s["StackName"] for s in _search(cfn, "list_stacks", "StackSummaries[]")
        if s["StackStatus"] in LIVE_STACK and is_project_name(s["StackName"]) and s["StackName"] != BUDGET_STACK
    ]
    found["cognito user pool"] = _search(session.client("cognito-idp"), "list_user_pools", "UserPools[].Name", MaxResults=60)
    gateways = _search(agentcore, "list_gateways", "items[]")
    found["agentcore gateway"] = [g["name"] for g in gateways]
    found["agentcore gateway target"] = [
        f'{g["name"]}/{t}'
        for g in gateways if is_project_name(g["name"])
        for t in _search(agentcore, "list_gateway_targets", "items[].name", gatewayIdentifier=g["gatewayId"])
    ]
    engines = _search(agentcore, "list_policy_engines", "policyEngines[]")
    found["agentcore policy engine"] = [e["name"] for e in engines]
    found["agentcore policy"] = [
        f'{e["name"]}/{p}'
        for e in engines if is_project_name(e["name"])
        for p in _search(agentcore, "list_policies", "policies[].name", policyEngineId=e["policyEngineId"])
    ]
    found["lambda function"] = _search(session.client("lambda"), "list_functions", "Functions[].FunctionName")
    found["lambda log group"] = [
        n.removeprefix("/aws/lambda/")
        for n in _search(session.client("logs"), "describe_log_groups", "logGroups[].logGroupName", logGroupNamePrefix="/aws/lambda/")
    ]
    found["log delivery source"] = _search(session.client("logs"), "describe_delivery_sources", "deliverySources[].name")
    found["iam role"] = _search(session.client("iam"), "list_roles", "Roles[].RoleName")
    found["secret"] = [
        n for n in _search(session.client("secretsmanager"), "list_secrets", "SecretList[].Name")
        if n.startswith(SECRET_PREFIX)
    ]
    return {kind: sorted(n for n in names if is_project_name(n) or kind in ("secret", "agentcore gateway target", "agentcore policy"))
            for kind, names in found.items()}


def present_budgets(session: boto3.Session) -> list[str]:
    account_id = session.client("sts").get_caller_identity()["Account"]
    names = _search(session.client("budgets"), "describe_budgets", "Budgets[].BudgetName", AccountId=account_id)
    return sorted(n for n in names if n in BUDGET_NAMES)
