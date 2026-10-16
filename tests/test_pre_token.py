from prior_auth.handlers.pre_token import handler, scalar_claims


def _event(groups):
    return {"version": "2", "triggerSource": "TokenGeneration_Authentication",
            "request": {"groupConfiguration": {"groupsToOverride": groups}}, "response": {}}


def test_clinician_in_one_tenant():
    assert scalar_claims(["clinician", "tenant-a"]) == {"pa_role": "clinician", "pa_tenant": "tenant-a"}


def test_staff_is_not_a_clinician():
    assert scalar_claims(["tenant-a"]) == {"pa_role": "none", "pa_tenant": "tenant-a"}


def test_two_tenants_or_none_gives_no_tenant():
    assert scalar_claims(["clinician", "tenant-a", "tenant-b"])["pa_tenant"] == "none"
    assert scalar_claims(["clinician"])["pa_tenant"] == "none"


def test_lookalike_groups_do_not_count():
    assert scalar_claims(["clinicians", "Clinician", "tenant-c"]) == {"pa_role": "none", "pa_tenant": "none"}


def test_handler_writes_access_token_claims_only():
    out = handler(_event(["clinician", "tenant-b"]), None)
    details = out["response"]["claimsAndScopeOverrideDetails"]
    assert details == {"accessTokenGeneration": {"claimsToAddOrOverride": {"pa_role": "clinician", "pa_tenant": "tenant-b"}}}


def test_handler_tolerates_missing_groups():
    out = handler({"request": {"groupConfiguration": None}, "response": {}}, None)
    assert out["response"]["claimsAndScopeOverrideDetails"]["accessTokenGeneration"]["claimsToAddOrOverride"] == {
        "pa_role": "none", "pa_tenant": "none"}
