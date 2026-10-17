"""The evidence bucket (beat 2 onward): packets, queue, recommendations, decisions.

Object Lock in governance mode (1-day default retention), versioning, one
customer-managed key, TLS only, and a bucket policy that lets each role write
only its own prefixes. Only the teardown role may bypass governance retention.
"""

from aws_cdk import Aws, Duration, RemovalPolicy, Stack, aws_iam as iam, aws_kms as kms, aws_s3 as s3
from constructs import Construct

from infra.names import EVIDENCE_BUCKET_PREFIX, EVIDENCE_KEY_ALIAS, PREFIX_WRITERS, ROLE_NAMES, WRITE_ONCE_PREFIXES


def role_arn(key: str) -> str:
    return f"arn:aws:iam::{Aws.ACCOUNT_ID}:role/{ROLE_NAMES[key]}"


def bucket_name() -> str:
    return f"{EVIDENCE_BUCKET_PREFIX}-{Aws.ACCOUNT_ID}"


class EvidenceStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)
        self.key = kms.Key(self, "EvidenceKey", alias=EVIDENCE_KEY_ALIAS, enable_key_rotation=True,
                           removal_policy=RemovalPolicy.DESTROY, pending_window=Duration.days(7))
        self.bucket = s3.Bucket(
            self, "EvidenceBucket", bucket_name=bucket_name(),
            encryption=s3.BucketEncryption.KMS, encryption_key=self.key, bucket_key_enabled=True,
            versioned=True, object_lock_enabled=True,
            object_lock_default_retention=s3.ObjectLockRetention.governance(Duration.days(1)),
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL, enforce_ssl=True,
            removal_policy=RemovalPolicy.RETAIN,  # emptied by the teardown role (governance bypass), then deleted
        )
        for prefix, writers in PREFIX_WRITERS.items():
            self.bucket.add_to_resource_policy(iam.PolicyStatement(
                sid=f"OnlyWriters{prefix.strip('/').title()}", effect=iam.Effect.DENY,
                principals=[iam.AnyPrincipal()], actions=["s3:PutObject"],
                resources=[self.bucket.arn_for_objects(f"{prefix}*")],
                conditions={"ArnNotEquals": {"aws:PrincipalArn": [role_arn(w) for w in writers]}},
            ))
        # Write-once enforced by storage, not by the writer's choice of header: a PUT to a
        # record prefix must be a conditional create (If-None-Match: *), and may never
        # replace an object by ETag (If-Match).
        records = [self.bucket.arn_for_objects(f"{p}*") for p in WRITE_ONCE_PREFIXES]
        self.bucket.add_to_resource_policy(iam.PolicyStatement(
            sid="RecordsAreCreateOnly", effect=iam.Effect.DENY, principals=[iam.AnyPrincipal()],
            actions=["s3:PutObject"], resources=records, conditions={"Null": {"s3:if-none-match": "true"}}))
        self.bucket.add_to_resource_policy(iam.PolicyStatement(
            sid="RecordsAreNeverReplaced", effect=iam.Effect.DENY, principals=[iam.AnyPrincipal()],
            actions=["s3:PutObject"], resources=records, conditions={"Null": {"s3:if-match": "false"}}))
        # A delete marker would let a later conditional create succeed and hide the record; only
        # the teardown role may delete under the record prefixes.
        self.bucket.add_to_resource_policy(iam.PolicyStatement(
            sid="RecordsAreNotDeleted", effect=iam.Effect.DENY, principals=[iam.AnyPrincipal()],
            actions=["s3:DeleteObject"], resources=records,
            conditions={"ArnNotEquals": {"aws:PrincipalArn": role_arn("teardown")}}))
        self.bucket.add_to_resource_policy(iam.PolicyStatement(
            sid="NoWritesOutsideKnownPrefixes", effect=iam.Effect.DENY, principals=[iam.AnyPrincipal()],
            actions=["s3:PutObject"],
            not_resources=[self.bucket.arn_for_objects(f"{p}*") for p in PREFIX_WRITERS],
        ))
        self.bucket.add_to_resource_policy(iam.PolicyStatement(
            sid="OnlyTeardownBypassesRetention", effect=iam.Effect.DENY, principals=[iam.AnyPrincipal()],
            actions=["s3:BypassGovernanceRetention", "s3:PutObjectRetention", "s3:DeleteObjectVersion"],
            resources=[self.bucket.arn_for_objects("*")],
            conditions={"ArnNotEquals": {"aws:PrincipalArn": role_arn("teardown")}},
        ))
        self.bucket.add_to_resource_policy(iam.PolicyStatement(
            sid="OnlyTheEvidenceKey", effect=iam.Effect.DENY, principals=[iam.AnyPrincipal()],
            actions=["s3:PutObject"], resources=[self.bucket.arn_for_objects("*")],
            conditions={"StringNotEqualsIfExists": {
                "s3:x-amz-server-side-encryption-aws-kms-key-id": self.key.key_arn}},
        ))
        iam.Role(self, "TeardownRole", role_name=ROLE_NAMES["teardown"],
                 assumed_by=iam.AccountRootPrincipal(),
                 inline_policies={"teardown": iam.PolicyDocument(statements=[iam.PolicyStatement(
                     # Version deletes only: no plain DeleteObject, so not even teardown can hide a
                     # record behind a delete marker.
                     actions=["s3:ListBucket", "s3:ListBucketVersions", "s3:DeleteObjectVersion",
                              "s3:BypassGovernanceRetention", "s3:DeleteBucket", "s3:GetObjectRetention"],
                     resources=[self.bucket.bucket_arn, self.bucket.arn_for_objects("*")])])})
