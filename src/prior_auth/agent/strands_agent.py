"""The Strands agent: it gathers the case through the agent gateway over MCP.

It is given exactly three gathering tools (G10). It returns citations only;
code fills each value from the trusted chart and decide() makes the decision.
"""

import json
import uuid

from botocore.exceptions import ClientError
from pydantic import BaseModel, Field
from strands import Agent
from strands.models import BedrockModel
from strands.types.exceptions import (MaxTokensReachedException, ModelThrottledException,
                                      StructuredOutputException)

from prior_auth import stores
from prior_auth.agent.pipeline import Extraction, ModelAccessDenied, ModelUnavailable
from prior_auth.decide import GatewayError

GATHERING_TOOLS = ("check_eligibility", "fetch_policy_criteria", "extract_clinical_evidence")
DEFAULT_MODEL = "amazon.nova-pro-v1:0"  # runtime default, us-east-1 only (design D8)

SYSTEM_PROMPT = """You gather evidence for one synthetic prior-authorization case. You do not decide it.
Use the tools: check eligibility, fetch the policy criteria, and read the case's documents.
For each criterion, cite the one line that states it, as document ID, page and line number.
Cite only lines returned by extract_clinical_evidence. If no line states a criterion, cite nothing for it.
Never quote text in a citation. Then write a two-sentence summary of the case."""


class Citation(BaseModel):
    criterion_id: str = Field(description="Criterion ID, for example C1")
    doc_id: str = Field(description="Document ID from extract_clinical_evidence")
    page: int
    line: int


class ExtractionOutput(BaseModel):
    citations: list[Citation]
    summary: str


def tool_short_name(name: str) -> str:
    return name.split("___", 1)[-1]


def gathering_tools(tools) -> list:
    """Keep exactly the three gathering tools, by exact name; the ending tools are never given."""
    return [t for t in tools if tool_short_name(t.tool_name) in GATHERING_TOOLS]


SAMPLING = {"temperature": 0, "max_tokens": 2048}


def sampling_sent(model: BedrockModel) -> dict:
    """The sampling settings exactly as the Bedrock request carries them (M5)."""
    request = model.format_request([{"role": "user", "content": [{"text": "x"}]}])
    return dict(request.get("inferenceConfig", {}))


def _usage(agent) -> dict:
    try:
        u = agent.event_loop_metrics.accumulated_usage
        return {"input_tokens": int(u.get("inputTokens", 0)), "output_tokens": int(u.get("outputTokens", 0))}
    except Exception:  # metrics never change an outcome
        return {}


def make_extract(mcp_client, model_id: str = DEFAULT_MODEL, region: str = "us-east-1"):
    def extract(case_id: str) -> Extraction:
        request = stores.request(case_id)
        tools = gathering_tools(mcp_client.list_tools_sync())
        model = BedrockModel(model_id=model_id, region_name=region, **SAMPLING)
        agent = Agent(model=model, tools=tools, system_prompt=SYSTEM_PROMPT, callback_handler=None)
        meta = lambda: {"model_id": model_id, "sampling": sampling_sent(model), "usage": _usage(agent)}
        prompt = (f"Case {case_id}. Member {request['member_id']}, payer {request['payer_id']}, "
                  f"CPT {request['cpt_code']}. Gather the evidence and cite it.")
        try:
            result = agent(prompt, structured_output_model=ExtractionOutput)
        except ModelThrottledException as e:
            raise ModelUnavailable(str(e)) from e
        except MaxTokensReachedException:
            return Extraction(stop_reason="max_tokens", meta=meta())
        except StructuredOutputException:
            return Extraction(malformed=True, stop_reason="structured_output_failed", meta=meta())
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "AccessDeniedException":
                raise ModelAccessDenied(str(e)) from e
            raise ModelUnavailable(str(e)) from e
        out = result.structured_output
        if out is None:
            return Extraction(malformed=True, stop_reason=str(result.stop_reason), meta=meta())
        return Extraction(citations=[c.model_dump() for c in out.citations], summary=out.summary,
                          stop_reason=str(result.stop_reason), meta=meta())
    return extract


def make_call(mcp_client):
    """call(action, arguments) for decide() and the pipeline, through the same agent identity."""
    def call(action: str, arguments: dict) -> dict:
        result = mcp_client.call_tool_sync(str(uuid.uuid4()), action, arguments)
        text = "".join(c.get("text", "") for c in result.get("content", []))
        if result.get("status") == "error" or result.get("isError"):
            raise GatewayError(text[:300] or "tool call failed")
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise GatewayError(f"unparseable tool result from {action}") from e
    return call
