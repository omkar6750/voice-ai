import { useEffect, useRef, useState } from "react";
import { useAuth } from "@clerk/react";
import { useApi, ApiError, useSupportSession } from "@/app/api";
import type { components } from "@/generated/api";
import type { AgentVersion } from "./types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { NativeSelect } from "@/components/ui/native-select";
import { Field, FieldLabel, FieldGroup } from "@/components/ui/field";
import {
  ChatTranscriptEntry,
  ChatInspection,
  transcriptEntries,
} from "./ChatEvidence";
import {
  MessageScroller,
  MessageScrollerProvider,
  MessageScrollerViewport,
  MessageScrollerContent,
  MessageScrollerItem,
  MessageScrollerButton,
} from "@/components/ui/message-scroller";

type Summary = components["schemas"]["ChatSummary"];
type Ticket = components["schemas"]["ChatTicket"];
type Setup = components["schemas"]["CreateChat"];
type Payload = Record<string, unknown>;
type Entry = {
  id: string;
  run_id: string;
  sequence: number;
  kind: string;
  payload: Payload;
  saved?: boolean;
};
type Detail = Summary & { messages: Entry[]; can_resume: boolean };
type Failure = {
  message: string;
  stage: string;
  diagnostic_id?: string;
  timestamp: string;
};
type Connection =
  "connecting" | "connected" | "reconnecting" | "paused" | "ended" | "failed";
const personas = {
  manual: "Write as the caller to test your own scenario.",
  interested:
    "You have a concrete need and are open to a callback. Ask about the offer.",
  hesitant:
    "You see some value but need reassurance. Ask specific questions before committing.",
  busy: "You have little time. Ask the agent to get to the point or call back later.",
  mismatch:
    "Your needs do not match the service. Explain why and check how the agent responds.",
  multilingual:
    "Switch naturally between your configured languages and clarify a detail.",
  opt_out:
    "Clearly decline contact and ask the agent to stop. Check that it respects this.",
};
function failure(error: unknown, stage: string): Failure {
  const diagnostic = error instanceof ApiError ? error.diagnostic : undefined;
  return {
    message: error instanceof Error ? error.message : "This operation failed.",
    stage: diagnostic?.stage ?? stage,
    diagnostic_id: diagnostic?.diagnostic_id,
    timestamp: diagnostic?.timestamp ?? new Date().toISOString(),
  };
}
function FailureNotice({ error }: { error: Failure }) {
  const [copyError, setCopyError] = useState("");
  return (
    <Alert variant="destructive">
      <AlertTitle>{error.stage} failed</AlertTitle>
      <AlertDescription>
        <p>{error.message}</p>
        <p className="font-mono text-xs tabular-nums">{error.timestamp}</p>
        {error.diagnostic_id && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              navigator.clipboard
                .writeText(error.diagnostic_id!)
                .catch(() =>
                  setCopyError(
                    "Could not copy. Select the diagnostic ID below.",
                  ),
                );
            }}
          >
            Copy diagnostic ID: {error.diagnostic_id}
          </Button>
        )}
        {copyError && <p>{copyError}</p>}
      </AlertDescription>
    </Alert>
  );
}

export function ChatTestPanel({
  version,
  dirty,
  save,
}: {
  version: AgentVersion;
  dirty: boolean;
  save: () => Promise<void>;
}) {
  const api = useApi();
  const { orgId } = useAuth();
  const supportSession = useSupportSession();
  const [history, setHistory] = useState<Summary[]>([]);
  const [contacts, setContacts] = useState<
    { id: string; name: string; phone_number: string }[]
  >([]);
  const [current, setCurrent] = useState<Summary | null>(null);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [state, setState] = useState<Connection>("paused");
  const [saving, setSaving] = useState("Saved");
  const [error, setError] = useState<Failure | null>(null);
  const [historyError, setHistoryError] = useState<Failure | null>(null);
  const [contactsError, setContactsError] = useState<Failure | null>(null);
  const [contactId, setContactId] = useState("");
  const [number, setNumber] = useState("");
  const [node, setNode] = useState("");
  const [background, setBackground] = useState("");
  const [scenario, setScenario] = useState<keyof typeof personas>("manual");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [selected, setSelected] = useState<Entry | null>(null);
  const [inspection, setInspection] = useState<unknown>(null);
  const [inspectorError, setInspectorError] = useState<Failure | null>(null);
  const [inspecting, setInspecting] = useState(false);
  const socket = useRef<WebSocket | null>(null);
  const active = useRef<Summary | null>(null);
  const sequence = useRef(0);
  const runtimeRun = useRef("");
  const mounted = useRef(true);
  const scopeEpoch = useRef(0);
  const connectionEpoch = useRef(0);
  const inspectorEpoch = useRef(0);
  const terminal = useRef(false);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnects = useRef(0);
  const pendingCommands = useRef(new Map<string, object>());

  async function loadHistory() {
    const epoch = scopeEpoch.current;
    try {
      const rows = await api<Summary[]>(
        `/chat-conversations?agent_version_id=${version.id}`,
      );
      if (mounted.current && epoch === scopeEpoch.current) {
        setHistory(rows);
        setHistoryError(null);
      }
    } catch (err) {
      if (mounted.current && epoch === scopeEpoch.current)
        setHistoryError(failure(err, "History"));
    }
  }
  async function loadContacts() {
    const epoch = scopeEpoch.current;
    try {
      const result = await api<{ contacts: typeof contacts }>("/contacts");
      if (mounted.current && epoch === scopeEpoch.current) {
        setContacts(result.contacts);
        setContactsError(null);
      }
    } catch (err) {
      if (mounted.current && epoch === scopeEpoch.current)
        setContactsError(failure(err, "Contacts"));
    }
  }
  useEffect(() => {
    mounted.current = true;
    scopeEpoch.current++;
    setContactId("");
    setNumber("");
    setBackground("");
    setText("");
    disconnect();
    setCurrent(null);
    setEntries([]);
    setHistory([]);
    setContacts([]);
    setState("paused");
    void loadHistory();
    void loadContacts();
    return () => {
      mounted.current = false;
      scopeEpoch.current++;
      connectionEpoch.current++;
      inspectorEpoch.current++;
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      socket.current?.close();
      socket.current = null;
    };
    // Tenant changes discard tickets, cached chat and pending commands.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [version.id, orgId, supportSession]);

  function upsert(entry: Entry) {
    setEntries((previous) => {
      const found = previous.findIndex((item) => item.id === entry.id);
      if (found < 0) return [...previous, entry];
      return previous.map((item, index) =>
        index === found ? { ...item, ...entry } : item,
      );
    });
  }
  function event(raw: string, runId: string) {
    let e: Payload;
    try {
      e = JSON.parse(raw) as Payload;
    } catch {
      setError(
        failure(
          new Error("Runtime sent an invalid stream event."),
          "Connection",
        ),
      );
      return;
    }
    if (typeof e.sequence === "number") {
      if (e.sequence <= sequence.current) return;
      sequence.current = e.sequence;
    }
    if (e.type === "message") {
      upsert({
        id: String(e.id),
        kind: String(e.kind),
        payload: e.payload as Payload,
        sequence: Number(e.sequence),
        run_id: runId,
        saved: false,
      });
      setSaving("Saving…");
    } else if (e.type === "generation_start") {
      setStreaming(true);
      upsert({
        id: String(e.id),
        kind: "assistant",
        payload: {
          text: "",
          status: "streaming",
          generation_id: e.generation_id,
        },
        sequence: Number(e.sequence),
        run_id: runId,
        saved: false,
      });
    } else if (e.type === "delta") {
      setEntries((previous) =>
        previous.map((item) =>
          item.id === e.id && item.payload.status === "streaming"
            ? {
                ...item,
                payload: {
                  ...item.payload,
                  text: String(item.payload.text ?? "") + String(e.text ?? ""),
                },
              }
            : item,
        ),
      );
    } else if (e.type === "generation_end") {
      setStreaming(false);
      setEntries((previous) =>
        previous.map((item) =>
          item.payload.generation_id === e.generation_id
            ? { ...item, payload: { ...item.payload, status: e.status } }
            : item,
        ),
      );
    } else if (e.type === "error") {
      setError({
        message: String(e.message),
        stage: String(e.stage),
        diagnostic_id: String(e.diagnostic_id ?? ""),
        timestamp: String(e.timestamp ?? new Date().toISOString()),
      });
    } else if (e.type === "persistence") {
      const ids = new Set((e.ids as string[]) ?? []);
      setEntries((previous) =>
        previous.map((item) =>
          ids.has(item.id) ? { ...item, saved: true } : item,
        ),
      );
      setSaving(
        e.state === "saved"
          ? "Saved"
          : e.state === "delayed"
            ? "Saving delayed"
            : "Saving…",
      );
    } else if (e.type === "command_ack") {
      pendingCommands.current.delete(String(e.id));
    } else if (e.type === "state") {
      setState(e.state as Connection);
      terminal.current = ["ended", "failed", "paused"].includes(
        String(e.state),
      );
      if (terminal.current) {
        setStreaming(false);
        void loadHistory();
      }
    }
  }

  async function connect(row: Summary, reconnect = false) {
    const epoch = ++connectionEpoch.current;
    setState(reconnect ? "reconnecting" : "connecting");
    setError(null);
    try {
      const ticket = await api<Ticket>(`/chat-conversations/${row.id}/ticket`, {
        method: "POST",
      });
      if (!mounted.current || epoch !== connectionEpoch.current) return;
      if (runtimeRun.current !== ticket.run_id) sequence.current = 0;
      runtimeRun.current = ticket.run_id;
      active.current = row;
      const url = new URL(ticket.ws_url);
      url.searchParams.set("after", String(sequence.current));
      const ws = new WebSocket(url);
      socket.current = ws;
      terminal.current = false;
      ws.onopen = () => {
        if (epoch !== connectionEpoch.current) {
          ws.close();
          return;
        }
        setState("connected");
        reconnects.current = 0;
        for (const command of pendingCommands.current.values())
          ws.send(JSON.stringify(command));
      };
      ws.onmessage = (message) => {
        if (epoch === connectionEpoch.current)
          event(String(message.data), ticket.run_id);
      };
      ws.onerror = () => {
        if (epoch === connectionEpoch.current)
          setError(
            failure(
              new Error(
                "Runtime connection failed. Check that the local runtime is running.",
              ),
              "Connection",
            ),
          );
      };
      ws.onclose = (close) => {
        if (
          !mounted.current ||
          epoch !== connectionEpoch.current ||
          terminal.current
        )
          return;
        setState("reconnecting");
        setStreaming(false);
        setEntries((previous) =>
          previous.map((item) =>
            item.payload.status === "streaming"
              ? { ...item, payload: { ...item.payload, status: "interrupted" } }
              : item,
          ),
        );
        if (close.code === 1008 || reconnects.current >= 3) {
          setState("failed");
          setError(
            failure(
              new Error(
                "Connection could not be restored. Reload saved history, then resume or start a new conversation.",
              ),
              "Connection",
            ),
          );
          return;
        }
        reconnects.current++;
        reconnectTimer.current = setTimeout(() => {
          void connect(row, true);
        }, 1000 * reconnects.current);
      };
    } catch (err) {
      if (epoch === connectionEpoch.current) {
        setError(failure(err, "Setup"));
        setState("failed");
      }
    }
  }

  function disconnect() {
    connectionEpoch.current++;
    inspectorEpoch.current++;
    if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
    socket.current?.close();
    socket.current = null;
    pendingCommands.current.clear();
    sequence.current = 0;
    runtimeRun.current = "";
    active.current = null;
    setStreaming(false);
    setSelected(null);
    setInspection(null);
    setError(null);
    setInspectorError(null);
  }
  async function start() {
    setBusy(true);
    setError(null);
    try {
      const setup: Setup = {
        agent_version_id: version.id,
        contact_id: contactId || null,
        whatsapp_number: number || null,
        starting_node: node || null,
        caller_background: background,
        scenario,
      };
      const row = await api<Summary>("/chat-conversations", {
        method: "POST",
        body: JSON.stringify(setup),
      });
      disconnect();
      setCurrent(row);
      active.current = row;
      setEntries([]);
      setSaving("Saved");
      await loadHistory();
      await connect(row);
    } catch (err) {
      setError(failure(err, "Setup"));
    } finally {
      setBusy(false);
    }
  }
  async function open(row: Summary) {
    disconnect();
    const epoch = connectionEpoch.current;
    setCurrent(row);
    setEntries([]);
    setBusy(true);
    try {
      const detail = await api<Detail>(`/chat-conversations/${row.id}`);
      if (!mounted.current || epoch !== connectionEpoch.current) return;
      setCurrent(detail);
      setEntries(detail.messages.map((item) => ({ ...item, saved: true })));
      setState(detail.status === "ended" ? "ended" : "paused");
      setSaving("Saved");
      if (detail.error) setError(detail.error as Failure);
    } catch (err) {
      setError(failure(err, "History"));
    } finally {
      setBusy(false);
    }
  }
  function command(type: string) {
    if (socket.current?.readyState !== WebSocket.OPEN) {
      setError(
        failure(
          new Error("Connect to the runtime before sending."),
          "Connection",
        ),
      );
      return;
    }
    const body = {
      type,
      id: crypto.randomUUID(),
      ...(type === "user_message" ? { text } : {}),
    };
    pendingCommands.current.set(body.id, body);
    socket.current.send(JSON.stringify(body));
    if (type === "user_message") setText("");
  }
  async function end() {
    if (!current) return;
    setBusy(true);
    try {
      if (socket.current?.readyState === WebSocket.OPEN) command("end");
      else
        await api(`/chat-conversations/${current.id}/end`, { method: "POST" });
      if (socket.current?.readyState !== WebSocket.OPEN) {
        terminal.current = true;
        setState("ended");
      }
      await loadHistory();
    } catch (err) {
      setError(failure(err, "End conversation"));
    } finally {
      setBusy(false);
    }
  }
  async function inspect(entry: Entry) {
    const epoch = ++inspectorEpoch.current;
    setSelected(entry);
    setInspection(null);
    setInspectorError(null);
    setInspecting(true);
    try {
      const details = await api(
        `/chat-conversations/${current!.id}/messages/${entry.id}`,
      );
      if (epoch === inspectorEpoch.current) setInspection(details);
    } catch (err) {
      if (epoch === inspectorEpoch.current)
        setInspectorError(failure(err, "Inspector"));
    } finally {
      if (epoch === inspectorEpoch.current) setInspecting(false);
    }
  }
  const effectiveNumber =
    number ||
    contacts.find((contact) => contact.id === contactId)?.phone_number ||
    "No destination selected";

  return (
    <section
      className="flex min-h-[36rem] flex-col gap-3"
      aria-label="Chat test workspace"
    >
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">Chat test</h2>
          <p className="text-xs text-muted-foreground">
            Testing saved revision {current?.revision ?? version.revision} ·
            Text only · LLM and integration costs apply
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="outline">Live tools</Badge>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              disconnect();
              setCurrent(null);
              setEntries([]);
              setState("paused");
            }}
          >
            New conversation
          </Button>
        </div>
      </header>
      {dirty && (
        <Alert>
          <AlertTitle>Unsaved changes are excluded</AlertTitle>
          <AlertDescription>
            Save first to test your latest edits.{" "}
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                void save().catch((err) =>
                  setError(failure(err, "Save configuration")),
                );
              }}
            >
              Save draft
            </Button>
          </AlertDescription>
        </Alert>
      )}
      <div className="grid min-h-[32rem] grid-cols-1 divide-y rounded-lg border bg-card lg:grid-cols-[12rem_minmax(0,1fr)] lg:divide-x lg:divide-y-0">
        <aside
          className="flex flex-col gap-2 p-3"
          aria-label="Saved conversations"
        >
          <h3 className="text-sm font-semibold">Conversations</h3>
          {historyError && (
            <>
              <FailureNotice error={historyError} />
              <Button
                variant="outline"
                size="sm"
                onClick={() => void loadHistory()}
              >
                Retry history
              </Button>
            </>
          )}
          {!history.length && !historyError && (
            <p className="text-xs text-muted-foreground">
              Start a conversation to test this saved version.
            </p>
          )}
          {history.map((row) => (
            <Button
              key={row.id}
              variant={current?.id === row.id ? "secondary" : "ghost"}
              className="h-auto justify-start whitespace-normal text-left"
              onClick={() => void open(row)}
            >
              <span className="flex flex-col gap-1">
                <span>{row.scenario.replaceAll("_", " ")}</span>
                <span className="text-xs tabular-nums">
                  {new Date(row.created_at).toLocaleString()} · {row.status}
                </span>
              </span>
            </Button>
          ))}
        </aside>
        <div className="flex min-w-0 flex-col lg:flex-row">
          <main className="flex min-w-0 flex-1 flex-col gap-3 p-4">
            {error && <FailureNotice error={error} />}
            {!current ? (
              <div className="flex flex-col gap-4">
                <h3 className="text-sm font-semibold">
                  Start a text conversation
                </h3>
                {contactsError && (
                  <>
                    <FailureNotice error={contactsError} />
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => void loadContacts()}
                    >
                      Retry contacts
                    </Button>
                  </>
                )}
                <FieldGroup>
                  <Field>
                    <FieldLabel htmlFor="chat-contact">Contact</FieldLabel>
                    <NativeSelect
                      id="chat-contact"
                      value={contactId}
                      onChange={(e) => setContactId(e.target.value)}
                    >
                      <option value="">No contact</option>
                      {contacts.map((contact) => (
                        <option key={contact.id} value={contact.id}>
                          {contact.name} · {contact.phone_number}
                        </option>
                      ))}
                    </NativeSelect>
                  </Field>
                  <Field>
                    <FieldLabel htmlFor="chat-number">
                      WhatsApp override (optional)
                    </FieldLabel>
                    <Input
                      id="chat-number"
                      value={number}
                      onChange={(e) => setNumber(e.target.value)}
                      placeholder="+919876543210"
                    />
                    <p className="text-xs text-muted-foreground">
                      Live destination: {effectiveNumber}
                    </p>
                  </Field>
                  <Field>
                    <FieldLabel htmlFor="chat-node">Starting node</FieldLabel>
                    <NativeSelect
                      id="chat-node"
                      value={node}
                      onChange={(e) => setNode(e.target.value)}
                    >
                      <option value="">Configured initial node</option>
                      {version.config.flow.nodes.map((n) => (
                        <option key={n.id} value={n.id}>
                          {n.id}
                        </option>
                      ))}
                    </NativeSelect>
                  </Field>
                  <Field>
                    <FieldLabel htmlFor="chat-persona">
                      Manual caller scenario
                    </FieldLabel>
                    <NativeSelect
                      id="chat-persona"
                      value={scenario}
                      onChange={(e) =>
                        setScenario(e.target.value as keyof typeof personas)
                      }
                    >
                      {Object.keys(personas).map((key) => (
                        <option key={key} value={key}>
                          {key.replaceAll("_", " ")}
                        </option>
                      ))}
                    </NativeSelect>
                    <p className="text-xs text-muted-foreground">
                      {personas[scenario]}
                    </p>
                  </Field>
                  <Field>
                    <FieldLabel htmlFor="chat-background">
                      Caller background (optional)
                    </FieldLabel>
                    <Textarea
                      id="chat-background"
                      value={background}
                      maxLength={4000}
                      onChange={(e) => setBackground(e.target.value)}
                      placeholder="Caller needs, prior discussion, or facts for this stage"
                    />
                    <p className="text-xs text-muted-foreground">
                      Background cannot confirm a booking or message send.
                    </p>
                  </Field>
                </FieldGroup>
                <Alert>
                  <AlertTitle>Tools perform real actions</AlertTitle>
                  <AlertDescription>
                    WhatsApp messages and callback bookings use the selected
                    contact and live integrations. No speech or telephone
                    services are used.
                  </AlertDescription>
                </Alert>
                <Button disabled={busy} onClick={() => void start()}>
                  {busy ? "Preparing…" : "Start conversation"}
                </Button>
              </div>
            ) : (
              <>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-col gap-1">
                    <span className="text-sm capitalize" role="status">
                      {state} · {saving}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      WhatsApp: {current.destination || "No destination"} ·{" "}
                      {personas[current.scenario as keyof typeof personas] ??
                        "Manual scenario"}
                    </span>
                  </div>
                  <div className="flex gap-2">
                    {state !== "connected" && state !== "ended" && (
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={
                          busy ||
                          state === "connecting" ||
                          state === "reconnecting"
                        }
                        onClick={() => void connect(current)}
                      >
                        Connect / resume
                      </Button>
                    )}
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busy || state === "ended"}
                      onClick={() => void end()}
                    >
                      End conversation
                    </Button>
                  </div>
                </div>
                <MessageScrollerProvider autoScroll>
                  <MessageScroller className="h-[26rem] min-h-0">
                    <MessageScrollerViewport>
                      <MessageScrollerContent className="flex flex-col gap-4">
                        {!entries.length && (
                          <p className="p-4 text-sm text-muted-foreground">
                            {state === "connecting"
                              ? "Preparing the agent…"
                              : "Connect to begin. The agent follows the selected node."}
                          </p>
                        )}
                        {transcriptEntries(entries).map((entry) => (
                          <MessageScrollerItem
                            key={entry.id}
                            messageId={entry.id}
                            scrollAnchor={entry.kind === "user"}
                          >
                            <ChatTranscriptEntry
                              entry={entry}
                              entries={entries}
                              inspect={(selectedEntry) =>
                                void inspect(selectedEntry)
                              }
                            />
                          </MessageScrollerItem>
                        ))}
                      </MessageScrollerContent>
                    </MessageScrollerViewport>
                    <MessageScrollerButton />
                  </MessageScroller>
                </MessageScrollerProvider>
                <form
                  className="flex flex-col gap-2"
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (text.trim()) command("user_message");
                  }}
                >
                  <Field>
                    <FieldLabel htmlFor="chat-input">Your message</FieldLabel>
                    <Textarea
                      id="chat-input"
                      value={text}
                      maxLength={8000}
                      disabled={state !== "connected"}
                      onChange={(e) => setText(e.target.value)}
                      onKeyDown={(e) => {
                        if (
                          e.key === "Enter" &&
                          !e.shiftKey &&
                          !e.nativeEvent.isComposing
                        ) {
                          e.preventDefault();
                          if (!e.repeat) e.currentTarget.form?.requestSubmit();
                        }
                      }}
                      placeholder="Type as the caller. Sending during a response interrupts it."
                    />
                  </Field>
                  <div className="flex justify-end gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      disabled={!streaming || state !== "connected"}
                      onClick={() => command("cancel")}
                    >
                      Stop response
                    </Button>
                    <Button
                      disabled={state !== "connected" || !text.trim()}
                      type="submit"
                    >
                      {streaming ? "Interrupt and send" : "Send"}
                    </Button>
                  </div>
                </form>
              </>
            )}
          </main>
          {selected && (
            <aside
              className="flex w-full shrink-0 flex-col gap-3 border-t p-4 lg:w-[28rem] lg:border-l lg:border-t-0"
              aria-label="Message inspector"
            >
              <header className="flex items-center justify-between gap-2">
                <h3 className="text-sm font-semibold">Message details</h3>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    inspectorEpoch.current++;
                    setSelected(null);
                  }}
                >
                  Close
                </Button>
              </header>
              {inspecting && (
                <p role="status" className="text-sm text-muted-foreground">
                  Loading context and traces…
                </p>
              )}
              {inspectorError && (
                <>
                  <FailureNotice error={inspectorError} />
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => void inspect(selected)}
                  >
                    Retry details
                  </Button>
                </>
              )}
              {inspection !== null && <ChatInspection value={inspection} />}
            </aside>
          )}
        </div>
      </div>
    </section>
  );
}
