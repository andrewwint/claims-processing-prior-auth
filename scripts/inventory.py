"""List every resource type this project creates, filtered to project names."""

import boto3

from infra.names import BUDGET_NAMES, BUDGET_STACK, PROJECT_TAG, SECRET_PREFIX, is_project_name

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
    found["log delivery destination"] = _search(session.client("logs"), "describe_delivery_destinations",
                                                "deliveryDestinations[].name")
    found["iam role"] = _search(session.client("iam"), "list_roles", "Roles[].RoleName")
    found["agentcore runtime"] = _search(agentcore, "list_agent_runtimes", "agentRuntimes[].agentRuntimeName")
    found["agentcore workload identity"] = _search(agentcore, "list_workload_identities", "workloadIdentities[].name")
    found["agentcore oauth2 credential provider"] = [
        p["name"] for p in agentcore.list_oauth2_credential_providers().get("credentialProviders", [])]
    found["s3 bucket"] = [b["Name"] for b in session.client("s3").list_buckets()["Buckets"]]
    found["runtime log group"] = [
        n.removeprefix("/aws/bedrock-agentcore/runtimes/")
        for n in _search(session.client("logs"), "describe_log_groups", "logGroups[].logGroupName",
                         logGroupNamePrefix="/aws/bedrock-agentcore/runtimes/")]
    # A deleted key stays PendingDeletion for its 7-day window; only an enabled key is a leftover.
    kms = session.client("kms")
    found["kms key (enabled)"] = [
        a["AliasName"].removeprefix("alias/") for a in _search(kms, "list_aliases", "Aliases[]")
        if "TargetKeyId" in a and kms.describe_key(KeyId=a["TargetKeyId"])["KeyMetadata"]["KeyState"] == "Enabled"
    ]
    found["secret"] = [
        s["Name"] for s in _search(session.client("secretsmanager"), "list_secrets", "SecretList[]")
        if s["Name"].startswith(SECRET_PREFIX)
        and {"Key": PROJECT_TAG[0], "Value": PROJECT_TAG[1]} in s.get("Tags", [])
    ]
    return {kind: sorted(n for n in names if is_project_name(n) or kind in ("secret", "agentcore gateway target", "agentcore policy"))
            for kind, names in found.items()}


def present_budgets(session: boto3.Session) -> list[str]:
    account_id = session.client("sts").get_caller_identity()["Account"]
    names = _search(session.client("budgets"), "describe_budgets", "Budgets[].BudgetName", AccountId=account_id)
    return sorted(n for n in names if n in BUDGET_NAMES)
