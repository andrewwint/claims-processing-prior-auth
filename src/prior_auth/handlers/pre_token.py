"""Cognito pre-token-generation trigger (event V2_0, user access tokens only).

Cedar sees an array claim such as cognito:groups as one String tag, so group
membership is restated as two scalar claims Cedar can compare exactly:
- pa_role:   "clinician" if the user is in the clinician group, else "none"
- pa_tenant: the user's single tenant group, else "none"
They are derived only from the pool's own group membership, never from client
input. Client-credentials (agent) tokens never reach a V2_0 trigger.
"""

TENANT_GROUPS = ("tenant-a", "tenant-b")


def scalar_claims(groups: list[str]) -> dict[str, str]:
    tenants = [g for g in groups if g in TENANT_GROUPS]
    return {
        "pa_role": "clinician" if "clinician" in groups else "none",
        "pa_tenant": tenants[0] if len(tenants) == 1 else "none",
    }


def handler(event, context):
    groups = (event.get("request", {}).get("groupConfiguration", {}) or {}).get("groupsToOverride") or []
    event["response"] = {
        "claimsAndScopeOverrideDetails": {
            "accessTokenGeneration": {"claimsToAddOrOverride": scalar_claims(list(groups))},
        }
    }
    return event
