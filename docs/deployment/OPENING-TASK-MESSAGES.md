# Initial node task messages

An initial node with `respond_immediately: true` requires at least one nonempty
`user` task message. System, developer and assistant task messages do not satisfy
this requirement. Nodes that wait for the caller need no opening task.

In Flow > Task messages, add a user instruction such as:

> Introduce yourself using the greeting instructions, then wait for the caller.
> This is a runtime instruction, not caller speech.

Chat and voice use the saved instruction. The runtime no longer inserts a chat
opening instruction. Saves, publication and session resolution validate the
requirement. Existing versions remain readable; clone published versions and fix
the draft before testing or activating it. No saved prompts are migrated automatically.

Fallback LLM calls receive the current primary service's node system instruction,
plus the same conversation context and tools. The fallback's configured provider,
model and credentials remain its own.
