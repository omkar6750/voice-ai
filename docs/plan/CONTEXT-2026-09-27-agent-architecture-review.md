# Agent architecture review: preserved user context

Date: 2026-09-27. This file preserves the latest annotated request across conversation compaction. It is planning context, not an implementation approval or a change to published agent versions. No Codex API for manually compacting the app conversation was available; this document is the durable copy.

## Latest user request (verbatim)

> first compact the conversation but save the aslt few texts as is so as not to lose  all the annotations i have made in the response and then create separate plans in the docs for how to tachle each of the issues and enumerate the steps for each thing answer for any challenging any decision i have made and try to keep everythingn in the plans do not miss anything

## Annotation selections and user comments (verbatim)

1. Selected: “It is tightly focused, but assumes the caller wants an e-commerce business, while the system prompt offers broader custom software. Ask about their actual project first; branch to e-commerce details only when relevant”
   Comment: “the requirement of the intership assignemnt says to sell ecommerce services”
2. Selected: “It states an $8k–$15k package, 3–4 weeks, and a quarterly discount as facts. Keep these only if approved and current. Its instruction names clossing, but the node is closing.”
   Comment: “we should fix that and the prices are mock only for the assignment”
3. Selected: “This is the largest node: collecting a time, checking availability, booking, offering alternatives, and falling back to schedule_callback. Split it only if tests show repeated tool or confirmation errors; otherwise give it an explicit sequence and success/failure rules. It has an edge to closing, but the prompt does not tell the model when to use it.”
   Comment: “add closing in its prompt”
4. Selected: “It is marked terminal while asking permission to send a catalog and potentially waiting for an answer. The runtime adds a “deliver the terminal response now” instruction to terminal nodes, which conflicts with that question. Make the catalog offer a separate nonterminal step, or end directly.”
   Comment: “it shouold send the messag regardless without asking permission and say sorry id needed and thankyou for giving time”
5. Selected: “Use actual function names and exact argument shapes in prompts. #change_node(...) is just text to the model; the registered function is change_node with a required node argument. Keep each node prompt to: current objective → one next question or statement → exact conditions for each allowed tool → what to do on tool failure. Groq’s prompting guide likewise recommends clear, concise instructions and only the context needed for the response.”
   Comment: “the #change node is so the frontend formats the tool names properly and if the tool is not bound we can detect that at write time so maybe it should remove those # and stuff when building the prompt”
6. Selected: “example, if you adopt a verbatim opening, the initial node could say:  Plain text”
   Comment: “let sonly use the node one for now i will test the verbatim later”
7. Selected: “seeds it with contact and time variables, but does not yet use it much for facts learned during the conversation. That is precisely what Pipecat’s state management is for. A tool should update state after a confirmed outcome; a prompt should not have to infer a booking from old dialogue”
   Comment: “would that tool call to save state facts and the reasing of the result and instruction on how to save which fact would bloat right or is it not needed for this how does state saving work is it done by the llm”
8. Selected: “RESET replaces the context messages, including dialogue history; it does not merely remove prior task prompts. The dashboard’s current “Reset replaces task messages” description is too narrow. For this agent, retain APPEND while you need the caller’s project details, then add real summarization; use RESET only when losing that history is intentional. This matches both the installed FlowManager implementation and Pipecat’s”
   Comment: “im not sure if the reset completely remove the transcript messages i thought it just removed the previous nodes prompt check the run and in the dev/github/voice-api/data in that you can see more runs there i think only the node prompts are replaced and the user and assistant transcruipts stay the same check in the current repos run as well cause i have all nodes set to reset”
9. Selected: “For the final design, make a caller’s request to hang up possible from every relevant phase. For a normal close, distinguish “decide to close” from “audio has finished playing,” then terminate after playback completion. Pipecat Flows’ built-in end_conversation post-action illustrates the intended ordering, but this runtime currently rejects node entry/exit actions, so simply placing that action in the saved config will not work. I would test the actual SIM7600 hangup path after that ordering is implemented. The one available run cannot tell us what happened in your earlier end-call attempt.”
   Comment: “why dont wwe have entry exit actions”
10. Selected: “. Its result can include both excerpts and full hits, increasing the next request’s tokens. Without the older run evidence, I cannot say which stage dominated your calls. A later KB experiment should record tool start/end, embedding time, database time, result size, and next LLM latency.”
    Comment: “when a single kb tool is added it should query only that kbs chunks not the other ones”
11. Selected: “practical budget for a test call is to keep the recurring system instructions and phase prompt short, cap returned tool text, and reserve room for several foreground turns. Track a rolling minute of actual input/output tokens and Groq’s rate-limit headers; give the live reply priority over classifier or summary requests. On 429, respect retry-after and use a bounded spoken recovery rather than leaving the caller in unexplained silence. The available run’s token counts are null, so I cannot calculate its true TPM usage from evidence.”
    Comment: “in the frontend currelty i have no way to see how many tokens is the prompt that inm writing no also the tokens view in the runs page also doesnt show how many total tokens were used ho many tokens was the call total and tokens per llm call total input and output tokens etc check why that is”
12. Selected: “Pipecat offers background summarization that preserves recent dialogue and complete function-call pairs, and it can use a dedicated LLM. A summary request still consumes provider capacity, so using the same throttled Groq model mid-call may worsen the problem. Pipecat context summarization.”
    Comment: “we can use gemini and let it run it background until its answer returns so that it wont stall the agent we should have a start token limit like if this token limit is hit in llm call then start summarising so that contexrt is summarised and ppended cleanly on the next llm call after summariser result comes appended behind the last 2-3 messages or the node exhcnga or we can have node entry exit summarisation setting so that wehn you endter a node the older nodes transcript get summarised to what is absolutely necessary”
13. Selected: “The saved call_limits.interruptions_enabled flag is not read by the live pipeline, so changing that dashboard value currently will not tune barge-in. The same is true of the saved idle_timeout_secs for normal turn recovery.For the demo, a small e”
    Comment: “we need to fix this”
14. Selected: “he custom serial PCM transport should also be checked for capture quality, echo, and write/backpressure timing before treating every pause as a prompt proble”
    Comment: “there is no echo no backpressure voice is quite clear”
15. Selected: “Krisp VIVA: Yes, it is a plausible addition for this carrier path. Silero is only the current speech activity detector. Krisp offers separable voice isolation, VAD, streaming turn completion, and interruption prediction. The last two address different symptoms: turn completion can reduce waiting after a real answer; interruption prediction can distinguish a genuine barge-in from a backchannel. Its telephony isolation model targets cellular audio up to 16 kHz, and its VAD supports 8–48 kHz. It needs Krisp’s SDK, models, and key; check the Windows/Python deployment package before choosing it. I would first compare filtered versus unfiltered carrier recordings, then test isolation and interruption prediction while retaining Silero, rather than changing”
    Comment: “it requiors request to  use the sdk so lets skip that”
16. Selected: “Language switching: Use runtime settings updates only when you have a reliable language decision and a provider setting that needs changing. Pipecat supports STTUpdateSettingsFrame and TTSUpdateSettingsFrame. Your runtime currently creates Sarvam STT with only its model and fixes Sarvam TTS at en-IN; saved follow_caller_language and persist_requested_language are not applied by the live host. Pipecat service settings.”
    Comment: “we should remove those configs and check for any other like those that might be in th eschema and dashboard but dont do anything”
17. Selected: “special characters. So first fix the LLM instruction conflict and evaluate actual generated text; then switch TTS to hi-IN, mr-IN, or te-IN on a confirmed language preference, without announcing the switch. Keep the selected language in flow state. Automatic STT language recognition does not by itself make the LLM maintain grammar or prevent “I will now speak in Marathi”
    Comment: “lets skip language change for now then”
18. Selected: “Cartesia: Pipecat 1.11 already exposes generation_config with volume, speed, and emotion, plus pronunciation_dict_id; the runtime only passes model, voice, and language today. Those belong in Cartesia-specific TTS configuration with validation and model/voice compatibility checks. The existing pace field is wired only for Sarvam and should not be presented as controlling Cartesia”
    Comment: “we should have a schema for these provider spwecific config and save them properly if they are used in the agent and also show those controls in the dashboard”

## Earlier decisions still in scope

- This is an internship assignment to sell e-commerce services; package prices and discounts are mock assignment data.
- Use the LLM-generated opening in the greeting node for now. Leave the existing verbatim `config.greeting` feature untested and unchanged.
- Do not touch classifier implementation; another agent is working on it.
- The request is for separate implementation plans and answers, not runtime/dashboard implementation.
- Skip Krisp VIVA and automatic language switching for now.
- The user reports clear carrier audio without echo or backpressure.

## Subsequent instruction (verbatim)

> no need for backward compatibility remove those fields from the db aswell keep it clean no need to build any compatibility

> fix everything defer the flow states for now and additional variables we need to talk more about that first then first make the smallest fixes in the prompt in the db create a new draft of the agent and make changes that we decided then do the smallest fixes first

The two inactive caller-language flags are removed from the active contract and all agent-version JSONB configurations. Historical run resolved snapshots are retained as evidence, not treated as reusable agent configuration. Flow-state facts and additional variables are deferred for discussion.

## Evidence boundary

- Current repo has one available run spool: `data/evidence/8b8e1318-ab15-4efb-8de7-7ace4da67759.jsonl`.
- `C:\Users\Omkar\dev\github\voice-api\data` was not present when checked. Recheck if the user supplies another path; do not invent earlier run findings.
- Pipecat 1.11.0 installed source sends `LLMMessagesUpdateFrame` for `RESET`, and the context aggregator calls `set_messages`, replacing the full message list. In the available run, the first five foreground LLM operations have 2, 4, 7, 9, and 13 context messages; earlier greeting/user/assistant/tool messages accumulate across transitions. This is APPEND-like observed behavior, regardless of what may currently be saved in a newer draft. The run is not evidence of RESET preserving history. The separate classifier work's PLAN-0019 says RESET retains history; that statement is inconsistent with the installed implementation and needs its own owner to reconcile.
