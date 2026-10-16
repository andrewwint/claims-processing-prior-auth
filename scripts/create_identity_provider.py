"""Post-deploy (beat 2): the AgentCore Identity OAuth2 provider for the agent's M2M token.

Reads the agent client's secret from Cognito in memory and hands it to the
Identity token vault; the secret is never printed, written to disk, or put in a
template. The runtime then obtains gateway tokens with requires_access_token(M2M).

Usage: python -m scripts.create_identity_provider
"""

import sys

import boto3
from botocore.exceptions import ClientError

from infra.names import IDENTITY_PROVIDER_NAME
from scripts import gateway_client as gc


def provider_config(out: dict, client_secret: str) -> dict:
    discovery = f"https://cognito-idp.us-east-1.amazonaws.com/{out['UserPoolId']}/.well-known/openid-configuration"
    return {"customOauth2ProviderConfig": {"oauthDiscovery": {"discoveryUrl": discovery},
                                           "clientId": out["AgentClientId"], "clientSecret": client_secret}}


def main() -> int:
    session = boto3.Session(region_name="us-east-1")
    out = gc.outputs()
    secret = session.client("cognito-idp").describe_user_pool_client(
        UserPoolId=out["UserPoolId"], ClientId=out["AgentClientId"])["UserPoolClient"]["ClientSecret"]
    control = session.client("bedrock-agentcore-control")
    try:
        try:
            control.create_oauth2_credential_provider(name=IDENTITY_PROVIDER_NAME, credentialProviderVendor="CustomOauth2",
                                                      oauth2ProviderConfigInput=provider_config(out, secret))
            print(f"created {IDENTITY_PROVIDER_NAME}")
        except control.exceptions.ConflictException:
            control.update_oauth2_credential_provider(name=IDENTITY_PROVIDER_NAME, credentialProviderVendor="CustomOauth2",
                                                      oauth2ProviderConfigInput=provider_config(out, secret))
            print(f"updated {IDENTITY_PROVIDER_NAME}")
        return 0
    except ClientError as e:
        print(f"Error: {e.response['Error']['Code']}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
