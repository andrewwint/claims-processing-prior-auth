"""Set a synthetic user's password for the workbench's hosted-UI sign-in.

The password is typed at a prompt and sent to Cognito only; it is not printed,
stored, or written to Secrets Manager. (The scripted paths rotate it again.)

Usage: python -m scripts.set_password [username]   (default syn-clinician-1)
"""

import getpass
import sys

import boto3

from scripts import gateway_client as gc


def main() -> int:
    username = sys.argv[1] if len(sys.argv) > 1 else "syn-clinician-1"
    password = getpass.getpass(f"New password for {username}: ")
    if password != getpass.getpass("Again: "):
        print("The passwords differ.", file=sys.stderr)
        return 1
    boto3.Session(region_name="us-east-1").client("cognito-idp").admin_set_user_password(
        UserPoolId=gc.outputs()["UserPoolId"], Username=username, Password=password, Permanent=True)
    print(f"Set. Sign in at http://localhost:8765/ as {username}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
