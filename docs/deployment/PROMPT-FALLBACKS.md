# Conversation facts and fallback prompts

In Flow → Conversation facts, give each fact a default or leave it Unset.
Unset is stored as an empty string for all types. Choose a typed value for a
nonempty default; numeric bounds and enums apply. Each new call or chat starts
again with these defaults. Record tools update facts only in that conversation.

Use canonical keys in prompts, for example:

```text
Speak in [ {{language}} | {{preferred_language}} ].
```

Here `language` is an exposed contact variable and `preferred_language` is a
declared string fact. The confirmed fact wins when nonempty; otherwise the
contact language wins. The Insert fallback picker can create and reorder longer
chains. Priority increases from left to right.

Empty strings, spaces and numeric zero fall back. String "0" and negative numbers
are values. Booleans cannot appear inside a chain but can be standalone variables.
If all candidates are empty, no text is inserted. Escape a literal expression:

```text
\[ {{language}} | {{preferred_language}} ]
```

In the Preview tab, enter contact/fact samples and choose Render preview, or
Try all empty. This uses unsaved edits without saving or calling providers. The
returned records explain the selected variable and why other values were empty.

Resolution happens when entering a node, not after every tool result. If a language
fact is recorded during greeting, its tool result is available immediately, but
the fallback inside the greeting instruction remains unchanged until node entry.
This feature does not change STT/TTS language settings or force a model to obey.

For new runs, select a flow visit in the run inspector → Prompt resolution. Compare
the values used on entry with the latest recorded facts, then use the linked LLM
operation to inspect the actual provider input. Historical runs without resolution
records show a coverage gap; current prompts are never used to fabricate evidence.

No database migration, agent update or publication is required. Restart local API
and runtime processes after integrating the code and rebuild/restart the dashboard.
Validate with fake-provider tests first; real-call acceptance remains operator-run.
