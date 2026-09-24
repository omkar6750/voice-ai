import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft,
  Bot,
  CheckCircle2,
  Copy,
  Layers,
  Lock,
  Plus,
  Radio,
  Save,
  Send,
  Sparkles,
  Trash2,
  UploadCloud,
} from "lucide-react";
import { toast } from "sonner";
import { useApi } from "@/app/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Field, FieldLabel } from "@/components/ui/field";
import { NativeSelect } from "@/components/ui/native-select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Spinner } from "@/components/ui/spinner";
import { Skeleton } from "@/components/ui/skeleton";
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from "@/components/ui/empty";
import type {
  AgentConfig,
  AgentVersionSummary,
  FlowNodeConfig,
} from "@/types/api";

export function AgentVersionPage() {
  const { agentId, versionId } = useParams();
  const api = useApi();
  const navigate = useNavigate();

  const [version, setVersion] = useState<AgentVersionSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [error, setError] = useState("");

  // Editable config state
  const [systemPrompt, setSystemPrompt] = useState("");
  const [nodes, setNodes] = useState<FlowNodeConfig[]>([]);
  const [initialNode, setInitialNode] = useState("greeting");
  const [llmModel, setLlmModel] = useState("llama-3.3-70b-versatile");
  const [llmTemp, setLlmTemp] = useState(0.7);
  const [sttLang, setSttLang] = useState("en");
  const [ttsVoice, setTtsVoice] = useState("sonic-english");
  const [maxDuration, setMaxDuration] = useState(300);
  const [revisionNote, setRevisionNote] = useState("");

  async function load() {
    if (!agentId) return;
    setLoading(true);
    setError("");
    try {
      const data = await api<{ versions: AgentVersionSummary[] }>(
        `/agents/${agentId}/versions`,
      );
      const current = data.versions.find((item) => item.id === versionId) ?? null;
      if (!current) {
        setError("Version not found for this agent.");
      } else {
        setVersion(current);
        const cfg = current.config;
        setSystemPrompt(cfg.system_prompt || "");
        setNodes(cfg.flow?.nodes || []);
        setInitialNode(cfg.flow?.initial_node || "greeting");
        setLlmModel(cfg.llm?.model || "llama-3.3-70b-versatile");
        setLlmTemp(cfg.llm?.temperature ?? 0.7);
        setSttLang(cfg.stt?.language || "en");
        setTtsVoice(cfg.tts?.voice || "sonic-english");
        setMaxDuration(cfg.call_limits?.max_duration_seconds || 300);
        setRevisionNote(current.note || "");
      }
    } catch (cause) {
      const message =
        cause instanceof Error ? cause.message : "Could not load version";
      setError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [agentId, versionId]);

  function buildConfigPayload(): AgentConfig {
    return {
      system_prompt: systemPrompt.trim(),
      flow: {
        initial_node: initialNode,
        nodes: nodes.map((n) => ({
          id: n.id,
          prompt: n.prompt.trim(),
          transitions: n.transitions || [],
          tool_bindings: n.tool_bindings || [],
          entry_actions: n.entry_actions || [],
          exit_actions: n.exit_actions || [],
          respond_immediately: n.respond_immediately ?? true,
          terminal: (n.transitions || []).length === 0,
        })),
        prompt_composition: "node_only",
      },
      llm: {
        provider: "groq",
        model: llmModel,
        temperature: Number(llmTemp),
      },
      stt: {
        provider: "deepgram",
        model: "nova-3",
        language: sttLang,
      },
      tts: {
        provider: "cartesia",
        voice: ttsVoice,
      },
      vad: {
        provider: "silero",
        confidence: 0.5,
      },
      call_limits: {
        max_duration_seconds: Number(maxDuration),
        silence_timeout_seconds: 30,
      },
    };
  }

  async function handleSaveDraft() {
    if (!version || version.status !== "draft") return;
    setSaving(true);
    try {
      const payload = {
        revision: version.revision,
        config: buildConfigPayload(),
        note: revisionNote.trim() || undefined,
      };

      const res = await api<{ id: string; revision: number; config: AgentConfig }>(
        `/agent-versions/${version.id}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
      );

      toast.success(`Draft updated to revision r${res.revision}`);
      await load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to save draft");
    } finally {
      setSaving(false);
    }
  }

  async function handlePublish() {
    if (!version || version.status !== "draft") return;
    if (!confirm("Are you sure you want to publish this draft? Published versions become immutable.")) {
      return;
    }
    setPublishing(true);
    try {
      await api(`/agent-versions/${version.id}/publish`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ revision: version.revision }),
      });
      toast.success(`Version v${version.version} published successfully!`);
      await load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to publish version");
    } finally {
      setPublishing(false);
    }
  }

  async function handleCloneDraft() {
    if (!version) return;
    try {
      const res = await api<{ version_id: string }>(
        `/agent-versions/${version.id}/clone`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ revision: version.revision }),
        },
      );
      toast.success("Created new draft version");
      navigate(`/agents/${agentId}/versions/${res.version_id}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to clone draft");
    }
  }

  function addNode() {
    const newId = `node_${nodes.length + 1}`;
    setNodes([
      ...nodes,
      {
        id: newId,
        prompt: "Describe what the agent should say and listen for at this step.",
        transitions: [],
        respond_immediately: true,
        terminal: true,
      },
    ]);
  }

  function removeNode(index: number) {
    if (nodes.length <= 1) {
      toast.error("An agent flow must have at least one node.");
      return;
    }
    const removedId = nodes[index].id;
    const remaining = nodes.filter((_, i) => i !== index);
    // Remove transitions pointing to removed node
    const updated = remaining.map((n) => ({
      ...n,
      transitions: (n.transitions || []).filter((t) => t !== removedId),
    }));
    setNodes(updated);
    if (initialNode === removedId && updated.length > 0) {
      setInitialNode(updated[0].id);
    }
  }

  function updateNode(index: number, updates: Partial<FlowNodeConfig>) {
    const updated = [...nodes];
    updated[index] = { ...updated[index], ...updates };
    setNodes(updated);
  }

  if (loading) {
    return (
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-4 p-6">
        <Skeleton className="h-6 w-36" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (!version) {
    return (
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-4 p-6">
        <Empty>
          <EmptyHeader>
            <EmptyTitle>Version unavailable</EmptyTitle>
            <EmptyDescription>{error || "Version not found."}</EmptyDescription>
          </EmptyHeader>
          <Button asChild variant="outline" size="sm">
            <Link to={`/agents/${agentId}`}>Back to Agent</Link>
          </Button>
        </Empty>
      </div>
    );
  }

  const isDraft = version.status === "draft";

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-5 p-6">
      {/* Header */}
      <div>
        <Link
          to={`/agents/${agentId}`}
          className="mb-2 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="size-3.5" /> Back to agent versions
        </Link>
        <div className="flex flex-wrap items-center justify-between gap-3 mt-1">
          <div className="flex items-center gap-3">
            <div className="flex size-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Bot className="size-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-semibold tracking-tight">
                  Agent Version v{version.version}
                </h1>
                <Badge
                  variant="outline"
                  className={
                    isDraft
                      ? "bg-amber-50 text-amber-700 border-amber-200 text-xs"
                      : "bg-emerald-50 text-emerald-700 border-emerald-200 text-xs"
                  }
                >
                  {isDraft ? `Draft (r${version.revision})` : `Published (r${version.revision})`}
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground font-mono mt-0.5">
                Version ID: {version.id}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {!isDraft && (
              <Button size="sm" variant="outline" onClick={() => void handleCloneDraft()}>
                <Copy className="size-3.5 mr-1.5" /> Clone as New Draft
              </Button>
            )}
            {isDraft && (
              <>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={saving}
                  onClick={() => void handleSaveDraft()}
                >
                  <Save className="size-3.5 mr-1.5" />
                  {saving ? "Saving…" : "Save Draft"}
                </Button>
                <Button
                  size="sm"
                  className="bg-emerald-600 hover:bg-emerald-700 text-white"
                  disabled={publishing}
                  onClick={() => void handlePublish()}
                >
                  <UploadCloud className="size-3.5 mr-1.5" />
                  {publishing ? "Publishing…" : "Publish Version"}
                </Button>
              </>
            )}
          </div>
        </div>
      </div>

      {!isDraft && (
        <div className="flex items-center gap-2 rounded-md border border-amber-200 bg-amber-50/50 p-3 text-xs text-amber-900">
          <Lock className="size-4 shrink-0 text-amber-600" />
          <span>
            This published version is immutable and locked for modification. To make changes, click <strong>Clone as New Draft</strong>.
          </span>
        </div>
      )}

      {/* Tabs */}
      <Tabs defaultValue="flow" className="w-full">
        <TabsList className="grid w-full grid-cols-3 max-w-md">
          <TabsTrigger value="flow">Prompt Graph Flow</TabsTrigger>
          <TabsTrigger value="persona">System Persona</TabsTrigger>
          <TabsTrigger value="runtime">AI Providers & Audio</TabsTrigger>
        </TabsList>

        {/* Tab 1: Flow Nodes */}
        <TabsContent value="flow" className="flex flex-col gap-4 pt-3">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <span className="text-xs font-medium text-muted-foreground">Initial Node:</span>
              <NativeSelect
                value={initialNode}
                disabled={!isDraft}
                onChange={(e) => setInitialNode(e.target.value)}
                className="h-8 text-xs font-mono w-44"
              >
                {nodes.map((n) => (
                  <option key={n.id} value={n.id}>
                    {n.id}
                  </option>
                ))}
              </NativeSelect>
            </div>
            {isDraft && (
              <Button size="sm" variant="outline" onClick={addNode}>
                <Plus className="size-3.5 mr-1.5" /> Add Flow Node
              </Button>
            )}
          </div>

          <div className="grid gap-4">
            {nodes.map((node, idx) => (
              <Card key={idx} className="shadow-none border">
                <CardHeader className="p-4 pb-3">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="flex size-6 items-center justify-center rounded bg-muted text-xs font-mono font-semibold">
                        {idx + 1}
                      </span>
                      <Input
                        value={node.id}
                        disabled={!isDraft}
                        placeholder="node_id"
                        className="h-7 text-xs font-mono font-semibold w-40"
                        onChange={(e) => updateNode(idx, { id: e.target.value })}
                      />
                      {initialNode === node.id && (
                        <Badge variant="outline" className="bg-blue-50 text-blue-700 text-[10px] border-blue-200">
                          Initial Entry
                        </Badge>
                      )}
                    </div>
                    {isDraft && (
                      <Button
                        variant="ghost"
                        size="icon-xs"
                        className="text-muted-foreground hover:text-destructive"
                        onClick={() => removeNode(idx)}
                      >
                        <Trash2 className="size-3.5" />
                      </Button>
                    )}
                  </div>
                </CardHeader>
                <CardContent className="p-4 pt-0 flex flex-col gap-3">
                  <Field>
                    <FieldLabel htmlFor={`prompt-${idx}`} className="text-xs">
                      Node Prompt & Conversation Goal
                    </FieldLabel>
                    <Textarea
                      id={`prompt-${idx}`}
                      rows={3}
                      disabled={!isDraft}
                      placeholder="Instruct the agent what to ask or say at this step..."
                      className="text-xs font-sans"
                      value={node.prompt}
                      onChange={(e) => updateNode(idx, { prompt: e.target.value })}
                    />
                  </Field>

                  <div className="flex flex-wrap items-center justify-between gap-4 pt-1">
                    <div className="flex items-center gap-2">
                      <span className="text-[11px] text-muted-foreground">Allowed Transitions:</span>
                      <Input
                        value={(node.transitions || []).join(", ")}
                        disabled={!isDraft}
                        placeholder="e.g. node_2, closing"
                        className="h-7 text-xs font-mono max-w-xs"
                        onChange={(e) =>
                          updateNode(idx, {
                            transitions: e.target.value
                              .split(",")
                              .map((s) => s.trim())
                              .filter(Boolean),
                          })
                        }
                      />
                    </div>

                    <div className="flex items-center gap-2">
                      <input
                        id={`resp-imm-${idx}`}
                        type="checkbox"
                        disabled={!isDraft}
                        checked={node.respond_immediately ?? true}
                        onChange={(e) =>
                          updateNode(idx, { respond_immediately: e.target.checked })
                        }
                        className="size-3.5 rounded border-gray-300 text-primary"
                      />
                      <label htmlFor={`resp-imm-${idx}`} className="text-xs text-muted-foreground">
                        Speak immediately upon node entry
                      </label>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        {/* Tab 2: System Persona */}
        <TabsContent value="persona" className="flex flex-col gap-4 pt-3">
          <Card className="shadow-none">
            <CardHeader className="p-4">
              <CardTitle className="text-sm">Global System Instructions</CardTitle>
              <CardDescription className="text-xs">
                Defines the persona, voice tone, conversational pacing, and safety boundaries across all flow nodes.
              </CardDescription>
            </CardHeader>
            <CardContent className="p-4 pt-0 flex flex-col gap-4">
              <Field>
                <FieldLabel htmlFor="sys-prompt">System Prompt</FieldLabel>
                <Textarea
                  id="sys-prompt"
                  rows={8}
                  disabled={!isDraft}
                  placeholder="You are an empathetic, professional sales assistant..."
                  className="font-sans text-xs"
                  value={systemPrompt}
                  onChange={(e) => setSystemPrompt(e.target.value)}
                />
              </Field>

              <Field>
                <FieldLabel htmlFor="rev-note">Revision Changelog Note (Optional)</FieldLabel>
                <Input
                  id="rev-note"
                  disabled={!isDraft}
                  placeholder="e.g. Added price qualification questions"
                  className="text-xs"
                  value={revisionNote}
                  onChange={(e) => setRevisionNote(e.target.value)}
                />
              </Field>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Tab 3: AI Providers & Runtime Settings */}
        <TabsContent value="runtime" className="flex flex-col gap-4 pt-3">
          <Card className="shadow-none">
            <CardHeader className="p-4">
              <CardTitle className="text-sm">AI Models & Voice Parameters</CardTitle>
              <CardDescription className="text-xs">
                Configure provider bindings and speech synthesis parameters for this agent version.
              </CardDescription>
            </CardHeader>
            <CardContent className="p-4 pt-0 grid gap-4 sm:grid-cols-2">
              <Field>
                <FieldLabel htmlFor="rt-llm">LLM Provider & Model</FieldLabel>
                <NativeSelect
                  id="rt-llm"
                  disabled={!isDraft}
                  value={llmModel}
                  onChange={(e) => setLlmModel(e.target.value)}
                >
                  <option value="llama-3.3-70b-versatile">Groq Llama 3.3 70B Versatile</option>
                  <option value="llama-3.1-8b-instant">Groq Llama 3.1 8B Instant</option>
                  <option value="gemini-2.5-flash">Google Gemini 2.5 Flash</option>
                </NativeSelect>
              </Field>

              <Field>
                <FieldLabel htmlFor="rt-temp">Temperature ({llmTemp})</FieldLabel>
                <Input
                  id="rt-temp"
                  type="number"
                  step={0.1}
                  min={0.0}
                  max={1.5}
                  disabled={!isDraft}
                  value={llmTemp}
                  onChange={(e) => setLlmTemp(Number(e.target.value))}
                />
              </Field>

              <Field>
                <FieldLabel htmlFor="rt-stt">STT Model & Language</FieldLabel>
                <NativeSelect
                  id="rt-stt"
                  disabled={!isDraft}
                  value={sttLang}
                  onChange={(e) => setSttLang(e.target.value)}
                >
                  <option value="en">Deepgram Nova-3 (English)</option>
                  <option value="mr">Deepgram Nova-3 (Marathi)</option>
                  <option value="hi">Deepgram Nova-3 (Hindi)</option>
                </NativeSelect>
              </Field>

              <Field>
                <FieldLabel htmlFor="rt-tts">TTS Voice Synthesis</FieldLabel>
                <NativeSelect
                  id="rt-tts"
                  disabled={!isDraft}
                  value={ttsVoice}
                  onChange={(e) => setTtsVoice(e.target.value)}
                >
                  <option value="sonic-english">Cartesia Sonic (English)</option>
                  <option value="sonic-multilingual">Cartesia Sonic (Multilingual)</option>
                </NativeSelect>
              </Field>

              <Field>
                <FieldLabel htmlFor="rt-limit">Call Max Duration (seconds)</FieldLabel>
                <Input
                  id="rt-limit"
                  type="number"
                  min={30}
                  max={3600}
                  disabled={!isDraft}
                  value={maxDuration}
                  onChange={(e) => setMaxDuration(Number(e.target.value))}
                />
              </Field>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
