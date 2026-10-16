# Tasks (demo scope, PM 2026-10-16)

Delivers **beat 5**: a clinician decides on the routed case. It is demoed right after **beat 4**, in which the agent is refused the same tool.

- [ ] 1.1 Reviewer gateway: add `record_clinician_approval` next to `record_adverse_determination`, with a Cedar permit for clinicians only. Beat 1 shows both gateways' `tools/list` side by side.
- [ ] 1.2 Reviewer Lambda:
  - the denial reason is required (schema plus server-side check; empty and whitespace-only are refused)
  - each decision writes a decision record chained to the recommendation record
  - the reviewer identity is labeled "as asserted by the clinician app"
- [ ] 1.3 A single local page:
  - hosted-UI sign-in through a standard OAuth library that handles PKCE and `state`, bound to 127.0.0.1
  - the queue
  - the packet view, with "Not found", "extraction failed" and "no verified policy" labeled distinctly and the model summary marked
  - approve, or deny with a required reason, through the reviewer gateway under the clinician's token

  The queue and packets are read with the operator's local AWS credentials (single tenant, demo only; a README limitation).
- [ ] 1.4 Recorded:
  - beat 4: the agent refused at the authorizer and by Cedar (from D4)
  - beat 5: the clinician succeeds with the same tool
  - the decision record and its chain
  - a screenshot
