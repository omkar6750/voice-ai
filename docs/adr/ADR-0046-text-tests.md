# ADR-0046: Text tests share the voice conversation runtime

Status: Accepted. Local testing only.

Text tests use the existing runtime service and NativePipelineHost conversation construction with a text output adapter. They retain Pipecat Flows, provider selection, tools, classifier cadence, summarization, cancellation and evidence. Speech credential resolution, speech clients, VAD, telephony and audio capture are excluded.

The API owns frozen saved configurations, tenant-owned chat conversations, execution attempts and messages. Each attempt has a text_test Run for grants and trace compatibility. Text runs are excluded from voice lists and call counters. The browser connects with a short-lived single-use ticket and receives no provider or service credentials.

Finalized messages and recoverable checkpoints use acknowledged runtime synchronization. Tokens stream only to the browser. Evidence IDs, command IDs and replay sequences support reconnect without repeated writes. A new attempt restores context and flow bindings without running entry actions or regenerating prior responses. In-flight or uncertain business writes invalidate safe continuation; they are never automatically retried.

Errors retain partial output and diagnostic identifiers, independently of console payload logging. Exact prompt and context evidence is accessible only through tenant-authorized inspection. Live WhatsApp and calendar tools keep their existing API authorization; text WhatsApp recipients are bound to the selected contact/override.
