"""Cognito: one user pool, a client-credentials app client for the agent, and a
separate app client for clinicians. Self-signup is disabled; synthetic users are
created by scripts/create_users.py with passwords in Secrets Manager."""

from aws_cdk import Duration, RemovalPolicy, aws_cognito as cognito
from constructs import Construct

GROUPS = ("clinician", "tenant-a", "tenant-b")
RESOURCE_SERVER = "prior-auth"
SCOPE = "tools"


class Identity(Construct):
    def __init__(self, scope: Construct, construct_id: str):
        super().__init__(scope, construct_id)
        self.pool = cognito.UserPool(
            self,
            "Pool",
            user_pool_name="prior-auth-users",
            self_sign_up_enabled=False,
            sign_in_aliases=cognito.SignInAliases(username=True),
            password_policy=cognito.PasswordPolicy(min_length=16),
            removal_policy=RemovalPolicy.DESTROY,
        )
        self.domain = self.pool.add_domain(
            "Domain", cognito_domain=cognito.CognitoDomainOptions(domain_prefix=f"prior-auth-{self.node.addr[:12]}")
        )
        tools_scope = cognito.ResourceServerScope(scope_name=SCOPE, scope_description="Call gateway tools")
        server = self.pool.add_resource_server(
            "ResourceServer", identifier=RESOURCE_SERVER, scopes=[tools_scope]
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
        )
        self.clinician_client = self.pool.add_client(
            "ClinicianClient",
            user_pool_client_name="prior-auth-clinician",
            generate_secret=False,
            auth_flows=cognito.AuthFlow(user_password=True),
            access_token_validity=Duration.minutes(60),
        )
        for group in GROUPS:
            cognito.CfnUserPoolGroup(self, f"Group-{group}", user_pool_id=self.pool.user_pool_id, group_name=group)

    @property
    def discovery_url(self) -> str:
        return f"https://cognito-idp.us-east-1.amazonaws.com/{self.pool.user_pool_id}/.well-known/openid-configuration"
