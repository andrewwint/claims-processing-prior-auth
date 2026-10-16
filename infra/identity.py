"""Cognito: one user pool, a client-credentials app client for the agent, and a
separate app client for clinicians. Self-signup is disabled; synthetic users are
created by scripts/create_users.py with passwords in Secrets Manager."""

from aws_cdk import Duration, RemovalPolicy, aws_cognito as cognito
from constructs import Construct

GROUPS = ("clinician", "tenant-a", "tenant-b")
RESOURCE_SERVER = "prior-auth"
# The workbench runs locally; its OAuth callback is the only redirect allowed.
WORKBENCH_CALLBACK = "http://localhost:8765/callback"
WORKBENCH_LOGOUT = "http://localhost:8765/"
SCOPE = "tools"
INVOKE_SCOPE = "invoke"


class Identity(Construct):
    def __init__(self, scope: Construct, construct_id: str, *, domain_prefix: str):
        super().__init__(scope, construct_id)
        self.pool = cognito.UserPool(
            self,
            "Pool",
            user_pool_name="prior-auth-users",
            self_sign_up_enabled=False,
            sign_in_aliases=cognito.SignInAliases(username=True),
            password_policy=cognito.PasswordPolicy(min_length=16),
            # Essentials: needed for access-token customization (pre-token trigger V2_0).
            feature_plan=cognito.FeaturePlan.ESSENTIALS,
            removal_policy=RemovalPolicy.DESTROY,
        )
        # The prefix is a deploy-time value kept out of the repository, so the
        # public source does not reveal or pre-claim the token endpoint.
        self.domain = self.pool.add_domain(
            "Domain", cognito_domain=cognito.CognitoDomainOptions(domain_prefix=domain_prefix)
        )
        tools_scope = cognito.ResourceServerScope(scope_name=SCOPE, scope_description="Call gateway tools")
        invoke_scope = cognito.ResourceServerScope(scope_name=INVOKE_SCOPE, scope_description="Invoke the agent runtime")
        server = self.pool.add_resource_server(
            "ResourceServer", identifier=RESOURCE_SERVER, scopes=[tools_scope, invoke_scope]
        )
        self.agent_client = self.pool.add_client(
            "AgentClient",
            user_pool_client_name="prior-auth-agent",
            generate_secret=True,
            auth_flows=cognito.AuthFlow(),
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(client_credentials=True),
                scopes=[cognito.OAuthScope.resource_server(server, tools_scope)],
            ),
            access_token_validity=Duration.minutes(60),
            prevent_user_existence_errors=True,
        )
        # Client credentials only: no user sign-in flow, so the agent client can
        # never mint a user-subject token (an empty AuthFlow falls back to Cognito defaults).
        self.agent_client.node.default_child.add_property_override("ExplicitAuthFlows", ["ALLOW_REFRESH_TOKEN_AUTH"])
        # Clinician sign-in (PM, 2026-10-16; supersedes the earlier "OAuth off" fix):
        # authorization code + PKCE with a localhost callback only. The earlier risk was
        # the implicit grant delivering tokens to a third-party callback; neither remains.
        # The only password fallback is SRP, so a password never crosses the wire.
        # The intake client is the only caller the runtime admits (beat 2). Client credentials only.
        self.intake_client = self.pool.add_client(
            "IntakeClient",
            user_pool_client_name="prior-auth-intake",
            generate_secret=True,
            auth_flows=cognito.AuthFlow(),
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(client_credentials=True),
                scopes=[cognito.OAuthScope.resource_server(server, invoke_scope)],
            ),
            access_token_validity=Duration.minutes(60),
            prevent_user_existence_errors=True,
        )
        self.intake_client.node.default_child.add_property_override("ExplicitAuthFlows", ["ALLOW_REFRESH_TOKEN_AUTH"])
        self.clinician_client = self.pool.add_client(
            "ClinicianClient",
            user_pool_client_name="prior-auth-clinician",
            generate_secret=False,
            auth_flows=cognito.AuthFlow(user_srp=True),
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(authorization_code_grant=True, implicit_code_grant=False),
                scopes=[cognito.OAuthScope.OPENID, cognito.OAuthScope.COGNITO_ADMIN],
                callback_urls=[WORKBENCH_CALLBACK],
                logout_urls=[WORKBENCH_LOGOUT],
            ),
            supported_identity_providers=[cognito.UserPoolClientIdentityProvider.COGNITO],
            write_attributes=cognito.ClientAttributes(),
            access_token_validity=Duration.minutes(60),
            prevent_user_existence_errors=True,
        )
        for group in GROUPS:
            cognito.CfnUserPoolGroup(self, f"Group-{group}", user_pool_id=self.pool.user_pool_id, group_name=group)

    @property
    def discovery_url(self) -> str:
        return f"https://cognito-idp.us-east-1.amazonaws.com/{self.pool.user_pool_id}/.well-known/openid-configuration"
