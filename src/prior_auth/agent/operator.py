"""The operator signal for failures a reviewer can't fix (failure table: model access denied).

The runtime emits this metric; a CloudWatch alarm on it is the operator alert (F4).
"""

NAMESPACE = "PriorAuth/Operator"
METRIC = "ModelAccessDenied"


def emit_model_access_denied(cloudwatch, model_id: str) -> None:
    # The alarm watches the dimensionless metric; CloudWatch treats each dimension set as its own
    # metric, so the datapoint is published both without dimensions (alarmed) and with the model ID
    # (for diagnosis).
    cloudwatch.put_metric_data(
        Namespace=NAMESPACE,
        MetricData=[{"MetricName": METRIC, "Value": 1, "Unit": "Count"},
                    {"MetricName": METRIC, "Value": 1, "Unit": "Count",
                     "Dimensions": [{"Name": "ModelId", "Value": model_id}]}],
    )
