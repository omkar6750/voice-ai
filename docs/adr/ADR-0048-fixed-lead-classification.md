---
id: ADR-0048
title: Fixed lead classification and enum routing
status: Accepted
date: 2026-10-02
---

# Decision

`classify_lead` is application-owned, accepts no arguments, and uses three fixed
choice questions: lead_temperature (hot/warm/cold), service_fit
(strong_fit/possible_fit/poor_fit), and tone (receptive/hesitant/resistant).
Both LLM and JEV use the same criteria. Provider/model selection, credentials,
enablement and execution cadence remain agent settings. Prompts, questions,
labels and JEV endpoint/model are fixed by the runtime contract.

The API normalizes legacy custom classifier definitions into this fixed contract;
this does not rewrite stored published JSON. The runtime enforces the same contract
for existing snapshots. This is an intentional behavior change authorized by the
operator; agents previously relying on custom classifiers need a future separate tool.

The runtime accepts only complete valid answers and derives `classification_key`
in temperature|fit|tone order (27 combinations). The API provider catalog publishes
the criteria and enums; the dashboard consumes them for read-only explanations and
routing. Node and shared classifier routing offer a single field or all three answers.
Unassigned cases use the explicit default, initially stay. Empty mapping compilation
reduces to its default because Pipecat's branch schema requires a nonempty case map.

Existing lead_followup policies and followup_route mappings are retained without
changing their destinations. New routing uses raw fixed labels or classification_key.
Routed classifier tools await the actual result; stale node results and failures
cannot execute a classifier transition. Unrouted classification retains its existing
background delivery behavior. A failed classifier result remains visible evidence.

No automatic classifier builder, additional output dimensions or DB migration.

# Operator use

In Flow, select a node, open Tools and add classify_lead routing. Choose Branch on
tool result, select a result field, then assign destinations to the generated cases.
All three answers displays 27 cases. Save changes before starting a new test.
Shared routing is available in Shared tools when classify_lead is global.
The Classifier settings page displays the fixed criteria and locked LLM instructions.
Live classifier/provider acceptance remains an operator-run test.