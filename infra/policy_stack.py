"""Stack B (approval gate D2): the Cedar policies.

The policy engine itself lives in the gateway stack and is attached in ENFORCE
mode from the first deploy, so until this stack lands every tool call is
denied by default. The principal values come from real tokens recorded after
D1 (task 3.2), passed as deploy-time context.
"""

from aws_cdk import Stack, aws_bedrockagentcore as agentcore
from constructs import Construct

from infra.cedar import all_policies


class PolicyStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, *, engine_id: str, agent_arn: str, reviewer_arn: str,
                 agent_sub: str, tag_shape: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)
        statements = all_policies(agent_sub=agent_sub, agent_arn=agent_arn, reviewer_arn=reviewer_arn,
                                  tag_shape=tag_shape)
        for name, statement in statements.items():
            agentcore.CfnPolicy(
                self, name, name=name, policy_engine_id=engine_id,
                definition=agentcore.CfnPolicy.PolicyDefinitionProperty(
                    cedar=agentcore.CfnPolicy.CedarPolicyProperty(statement=statement)
                ),
                # Explicit: a policy in LOG_ONLY enforces nothing.
                enforcement_mode="ACTIVE",
                # validation_mode is left unset: the service default is FAIL_ON_ANY_FINDINGS,
                # and findings are recorded, never bypassed.
            )
