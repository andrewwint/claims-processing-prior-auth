forbid(
  principal is AgentCore::OAuthUser,
  action == AgentCore::Action::"ReviewerTools___record_adverse_determination",
  resource == AgentCore::Gateway::"<reviewer-gateway-arn>"
) when { principal == AgentCore::OAuthUser::"<agent-client-id>" || !(principal.hasTag("pa_role") && principal.getTag("pa_role") == "clinician") };
