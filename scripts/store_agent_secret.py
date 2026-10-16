"""Copy the agent app client's secret into Secrets Manager (post-deploy, D1).

The secret is read from Cognito and written to prior-auth/agent-client with the
project tag. It is never printed or written to disk.

Usage: python -m scripts.store_agent_secret <user-pool-id> <agent-client-id>
"""

import json
import sys

import boto3
from botocore.exceptions import ClientError

from infra.names import AGENT_SECRET, PROJECT_TAG


def store(cognito, secrets_client, pool_id: str, client_id: str) -> None:
    client = cognito.describe_user_pool_client(UserPoolId=pool_id, ClientId=client_id)["UserPoolClient"]
    value = json.dumps({"client_id": client_id, "client_secret": client["ClientSecret"]})
    try:
        secrets_client.create_secret(Name=AGENT_SECRET, SecretString=value,
                                     Tags=[{"Key": PROJECT_TAG[0], "Value": PROJECT_TAG[1]}])
    except secrets_client.exceptions.ResourceExistsException:
        secrets_client.put_secret_value(SecretId=AGENT_SECRET, SecretString=value)


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    session = boto3.Session(region_name="us-east-1")
    try:
        store(session.client("cognito-idp"), session.client("secretsmanager"), sys.argv[1], sys.argv[2])
        print(f"stored {AGENT_SECRET}")
        return 0
    except ClientError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
