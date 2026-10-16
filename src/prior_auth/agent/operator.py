"""The operator signal for failures a reviewer can't fix (failure table: model access denied).

The runtime emits this metric; a CloudWatch alarm on it is the operator alert (F4).
"""

NAMESPACE = "PriorAuth/Operator"
METRIC = "ModelAccessDenied"


def emit_model_access_denied(cloudwatch, model_id: str) -> None:
    cloudwatch.put_metric_data(
        Namespace=NAMESPACE,
        MetricData=[{"MetricName": METRIC, "Value": 1, "Unit": "Count",
                     "Dimensions": [{"Name": "ModelId", "Value": model_id}]}],
    )
