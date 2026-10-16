"""Admin-create the synthetic clinician and tenant users.

Passwords are generated here, set as permanent, and stored only in Secrets
Manager under prior-auth/users/<username>. They are never printed or written to disk.

Usage: python -m scripts.create_users <user-pool-id>
"""

import json
import secrets
import string
import sys

import boto3
from botocore.exceptions import ClientError

from infra.names import PROJECT_TAG, SECRET_PREFIX

USERS = {
    "syn-clinician-1": ["clinician", "tenant-a"],
    "syn-clinician-2": ["clinician", "tenant-b"],
    "syn-tenant-a-staff": ["tenant-a"],
    "syn-tenant-b-staff": ["tenant-b"],
}


def generate_password(length: int = 24) -> str:
    alphabet = string.ascii_letters + string.digits + "!#%+-=?_"
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(length))
        if (any(c.islower() for c in pw) and any(c.isupper() for c in pw)
                and any(c.isdigit() for c in pw) and any(c in "!#%+-=?_" for c in pw)):
            return pw


def create_user(cognito, secrets_client, pool_id: str, username: str, groups: list[str]) -> None:
    password = generate_password()
    try:
        cognito.admin_create_user(UserPoolId=pool_id, Username=username, MessageAction="SUPPRESS")
    except cognito.exceptions.UsernameExistsException:
        pass
    cognito.admin_set_user_password(UserPoolId=pool_id, Username=username, Password=password, Permanent=True)
    for group in groups:
        cognito.admin_add_user_to_group(UserPoolId=pool_id, Username=username, GroupName=group)
    name = f"{SECRET_PREFIX}users/{username}"
    value = json.dumps({"username": username, "password": password})
    try:
        secrets_client.create_secret(Name=name, SecretString=value,
                                     Tags=[{"Key": PROJECT_TAG[0], "Value": PROJECT_TAG[1]}])
    except secrets_client.exceptions.ResourceExistsException:
        secrets_client.put_secret_value(SecretId=name, SecretString=value)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    session = boto3.Session(region_name="us-east-1")
    cognito, sm = session.client("cognito-idp"), session.client("secretsmanager")
    try:
        for username, groups in USERS.items():
            create_user(cognito, sm, sys.argv[1], username, groups)
            print(f"created {username} in {groups}")
        return 0
    except ClientError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
