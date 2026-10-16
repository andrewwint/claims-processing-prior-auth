"""Every session ends in exactly one terminal outcome (F7)."""

import logging

TERMINAL = ("approved", "routed", "operator_alert", "needs_review")
logger = logging.getLogger(__name__)


class OutcomeRecorder:
    def __init__(self):
        self.outcome: dict | None = None
        self.violations = 0

    def set(self, outcome: dict) -> bool:
        if outcome.get("outcome") not in TERMINAL:
            raise ValueError(f"not a terminal outcome: {outcome.get('outcome')}")
        if self.outcome is not None:
            self.violations += 1
            logger.error("invariant violation: second terminal outcome refused")
            return False
        self.outcome = outcome
        return True


def run_session(body, route_needs_review) -> dict:
    """Run body(recorder); if it ends without an outcome, the case becomes needs_review and is routed."""
    recorder = OutcomeRecorder()
    try:
        body(recorder)
    except Exception as e:  # any escape still ends at a person
        logger.error("session raised %s", type(e).__name__)
    finally:
        if recorder.outcome is None:
            routed = route_needs_review()
            if routed.get("outcome") == "operator_alert":  # it could not even be routed
                recorder.set(routed)
            else:
                recorder.set({**routed, "outcome": "needs_review", "reason": "session ended without an outcome"})
    return recorder.outcome
