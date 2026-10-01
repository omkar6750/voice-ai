# Current and proposed agent config snapshots

This comparison shows the actual seeded starter agent shape and a proposed target shape for a lead qualification agent. The current snapshot is based on `organization_seed.py` and the `AgentConfig`/`FlowConfig` Pydantic contracts. Values such as tool IDs are omitted because they are generated per installation.

The **proposed `flow` object uses Pipecat field names**: `initial_node`, `global_functions`, `nodes`, `role_message`, `task_messages`, `functions`, `transition_to`, `pre_actions`, `post_actions`, `context_strategy`, and `respond_immediately`. The whole target is not yet directly loadable as Pipecat `FlowConfig`, because the outer app config still has versioned `tool_bindings` and operator `fact_slots`. Those stay outside `flow` and are resolved by the app adapter.

## Current saved shape (starter seed)

```yaml
name: Starter Voice Agent
system_prompt: >-
  You are a friendly, helpful voice assistant. Speak naturally and concisely.
  Ask one question at a time, listen carefully, and end the call politely when done.
greeting: ""
flow:
  initial_node: greeting
  prompt_composition: node_only
  nodes:
    - id: greeting
      prompt: >-
        Greet the caller and ask how you can help. When they are ready to continue,
        use change_node to move to conversation.
      context_strategy: append
      transitions: [conversation]
      tool_bindings: [change_node, end_call]
      entry_actions: []
      exit_actions: []
      respond_immediately: true
      terminal: false
    - id: conversation
      prompt: >-
        Help the caller with their request. Keep replies short and natural. When
        the caller is ready to finish, say goodbye and use end_call.
      context_strategy: append
      transitions: []
      tool_bindings: [end_call]
      entry_actions: []
      exit_actions: []
      respond_immediately: true
      terminal: true
tool_bindings:
  change_node: {tool_id: "<generated>", tool_version_id: "<generated>"}
  end_call: {tool_id: "<generated>", tool_version_id: "<generated>"}
```

The create-agent form currently makes an even smaller config and hard-codes `initial_node: greeting` with one `greeting` node. In the editor, `FlowPanel` already exposes an Initial node selector. `change_node` is a registered generic tool; the runtime constrains its node argument using `transitions`.

## Proposed target shape

```yaml
name: Elevated Box Lead Qualifier
filter_incomplete_user_turns: false # experiment cohort may override per call

# Pipecat FlowConfig fields begin here.
flow:
  initial_node: greeting

  # Available to the model from every node. Only put truly cross-node tools here.
  global_functions:
    - name: get_business_hours

  nodes:
    greeting:
      role_message: >-
        You are a concise, courteous voice assistant for Elevated Box. Ask one
        question at a time. Never claim an action succeeded unless its result
        confirms success. At this node, greet the caller and ask whether now
        is a good time.
      task_messages: []
      functions:
        - name: prepare_discovery
          transition_to: discovery
          # Python handler stores the caller's query in FlowManager.state.
        - name: request_callback
          transition_only: true
          description: The caller is busy and wants a callback.
          transition_to: book_callback
        - name: decline_call
          transition_only: true
          description: The caller declines and wants to end the call.
          transition_to: closing
      context_strategy: append
      respond_immediately: true

    discovery:
      # role_message replaces the system instruction for this node.
      role_message: >-
        You are a concise, courteous voice assistant for Elevated Box. Ask
        focused discovery questions using {{ retrieval_result }} and save useful
        answers with the configured fact tools. Ask one question at a time and
        do not invent caller details.
      task_messages: []
      pre_actions:
        - type: tts_say
          text: Let me check that for you.
          append_text_to_context: true
        - type: function
          handler: run_pending_retrieval
      functions:
        - name: assess_qualification
          transition_to:
            field: status
            cases:
              qualified: book_callback
              unqualified: closing
              needs_more_information: discovery
            default: closing
        - name: request_callback
          transition_only: true
          description: The caller wants a callback instead of continuing now.
          transition_to: book_callback
        - name: decline_call
          transition_only: true
          description: The caller wants to end the call.
          transition_to: closing
      context_strategy: append
      respond_immediately: true

    book_callback:
      role_message: >-
        You are a concise, courteous voice assistant for Elevated Box. Confirm
        only callback details that the booking system verifies. Collect a
        preferred callback time and confirm only a successful booking.
      task_messages: []
      functions:
        - name: book_callback
          transition_to:
            field: status
            cases:
              booked: closing
              unavailable: book_callback
              failed: book_callback
        - name: decline_callback
          transition_only: true
          description: The caller no longer wants a callback and wants to end the call.
          transition_to: closing
      context_strategy: append
      respond_immediately: true

    closing:
      role_message: >-
        You are a concise, courteous voice assistant for Elevated Box. Briefly
        summarize confirmed outcomes, thank the caller, and say goodbye.
      task_messages: []
      post_actions:
        - type: end_conversation
      context_strategy: append
      respond_immediately: true

# App extension, deliberately outside Pipecat FlowConfig.
# The runtime compiles these definitions to constrained functions only on the
# named nodes. It validates the key and value again before writing FlowManager.state.
fact_slots:
  - key: budget_range
    description: Caller’s approximate budget
    value_type: string
    nodes: [discovery, book_callback]
  - key: decision_timeline
    description: When the caller expects to make a decision
    value_type: string
    nodes: [discovery, book_callback]

# App extension: names map to existing versioned tool definitions/handlers.
# It is not passed to Pipecat as a FlowConfig field.
tool_bindings:
  get_business_hours: {tool_id: "<configured>", tool_version_id: "<published>"}
  assess_qualification: {tool_id: "<configured>", tool_version_id: "<published>"}
  book_callback: {tool_id: "<configured>", tool_version_id: "<published>"}
  record_budget_range: {tool_id: "<generated-or-system>", tool_version_id: "<compiled>"}
  record_decision_timeline: {tool_id: "<generated-or-system>", tool_version_id: "<compiled>"}

# Existing LLM, STT, TTS, VAD, telephony, callback-calendar, credential-reference,
# classifier, context-summarizer and call-limit settings remain in AgentConfig.
```

## Field mapping and limits

| Current app field | Proposed Pipecat field or treatment |
| --- | --- |
| `flow.initial_node` | Keep `initial_node`; make it selectable during agent creation and editing. |
| `FlowNodeConfig.id` | Become the key under `flow.nodes`. |
| `FlowNodeConfig.prompt` | Merge into that node's `role_message` so its objective reaches provider system instructions; do not add it as a `user` task message. |
| `FlowNodeConfig.role_prompt` | Become `role_message`; allow an explicit role message on each node. |
| `FlowNodeConfig.context_strategy` | Keep `context_strategy` (`append`/`reset`). |
| `FlowNodeConfig.transitions` + `change_node` | Replace with function-level `transition_to`, transition-only functions, and branch tables. |
| `FlowNodeConfig.tool_bindings` | Resolve function names through app-side `tool_bindings`; do not pass that extension into FlowConfig. |
| `entry_actions` / `exit_actions` | Replace entry behavior with `pre_actions`; post-response behavior with `post_actions`. Keep only truly necessary custom exit logic. |
| `FlowNodeConfig.respond_immediately` | Keep `respond_immediately`. |
| `FlowNodeConfig.terminal` | No Pipecat node field. Represent graceful finish with `post_actions: [{type: end_conversation}]`; retain app-only terminal metadata only if evidence/UI needs it. |
| `FlowConfig.prompt_composition` | Remove after global/role precedence is migrated; it is not a Pipecat field. |
| `AgentConfig.system_prompt` | Migrate to the initial `role_message`, then remove or retain as a documented authoring shortcut—not as a second competing LLM instruction. |
| `global_functions` | Add as a Pipecat-native FlowConfig field and pass compiled handlers to `FlowManager(global_functions=...)`. |
| Operator facts | Add app-side `fact_slots`; compile to narrow callable schemas and state writes. Not a native FlowConfig field. |
| Turn completion experiment | Add app-side `filter_incomplete_user_turns: false`; the runtime maps experiment-group calls to `FilterIncompleteUserTurnStrategies`. This is not part of `FlowConfig` or VAD. |

`nodes` order can drive the dashboard's displayed order and be reordered there, but `initial_node` alone determines the start node. The node layout/reordering state is UI behavior and does not change graph routing. The proposed sample is a design target, not yet schema-valid as one object: the app must split native `flow` from app extensions and compile registered-tool schemas into Pipecat `FlowsFunctionSchema` where direct handler signatures do not preserve the existing constraints.
