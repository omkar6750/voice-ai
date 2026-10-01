"""Reference-validation stubs for example-lead-qualification-flow.yaml.

These deliberately perform no external business action. They are not call-ready.
"""

from pipecat.flows import TRANSITION_IN_YAML, FlowManager


async def collect_lead_fact(flow_manager: FlowManager, key: str, value: str):
    """Record a non-sensitive lead fact for this call.

    Args:
        key: Approved fact key; production code must validate against operator slots.
        value: Fact supplied by the caller; production code must validate it.
    """
    return {"status": "not_implemented"}, TRANSITION_IN_YAML


async def assess_qualification(flow_manager: FlowManager):
    """Assess the lead from verified facts in call state."""
    return {"status": "needs_more_information"}, TRANSITION_IN_YAML


async def book_callback(flow_manager: FlowManager, preferred_time: str):
    """Book a callback after checking availability.

    Args:
        preferred_time: The caller's preferred callback time.
    """
    return {"status": "failed"}, TRANSITION_IN_YAML
