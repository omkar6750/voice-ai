import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft,
  AudioLines,
  Bot,
  Brain,
  Check,
  CheckCircle2,
  Copy,
  Cpu,
  Database,
  Layers,
  Link2,
  ListTodo,
  Lock,
  Plus,
  Radio,
  RotateCw,
  Save,
  Send,
  Sliders,
  Sparkles,
  Trash2,
  Volume2,
  Wrench,
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
  KnowledgeBaseItem,
  ToolItem,
} from "@/types/api";

export function AgentVersionPage() {
  const { agentId, versionId } = useParams();
  const api = useApi();
  const navigate = useNavigate();

  const [version, setVersion] = useState<AgentVersionSummary | null>(null);
  const [allVersions, setAllVersions] = useState<AgentVersionSummary[]>([]);
  const [availableTools, setAvailableTools] = useState<ToolItem[]>([]);
  const [availableKBs, setAvailableKBs] = useState<KnowledgeBaseItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [error, setError] = useState("");

  // Agent Identity & Meta
  const [agentName, setAgentName] = useState("Agent");
  const [persona, setPersona] = useState("Voice agent for customer help and account support.");
  const [revisionNote, setRevisionNote] = useState("");

  // Runtime Mode
  const [runtimeMode, setRuntimeMode] = useState<"pipecat" | "cascaded" | "s2s">("pipecat");
  const [defaultLang, setDefaultLang] = useState("en-IN");
  const [supportedLanguages, setSupportedLanguages] = useState<string[]>([
    "en-IN",
    "hi-IN",
    "mr-IN",
    "te-IN",
  ]);
  const [followCallerLang, setFollowCallerLang] = useState(true);
  const [persistLang, setPersistLang] = useState(true);

  // Model & Prompts: Pipeline Configuration Islands
  // STT
  const [sttProvider, setSttProvider] = useState<"sarvam" | "deepgram">("sarvam");
  const [sttModel, setSttModel] = useState("saaras:v3");
  const [sttLang, setSttLang] = useState("en");
  const [sttSampleRate, setSttSampleRate] = useState<number>(8000);
  const [sttSensitivity, setSttSensitivity] = useState(0.6);
  const [partialTranscripts, setPartialTranscripts] = useState(true);

  // LLM
  const [llmProvider, setLlmProvider] = useState<"groq" | "google">("groq");
  const [llmModel, setLlmModel] = useState("llama-3.3-70b-versatile");
  const [llmTemp, setLlmTemp] = useState(0.7);
  const [llmMaxTokens, setLlmMaxTokens] = useState(180);
  const [enableToolCalling, setEnableToolCalling] = useState(true);

  // TTS
  const [ttsProvider, setTtsProvider] = useState<"sarvam" | "cartesia">("sarvam");
  const [ttsVoice, setTtsVoice] = useState("ritu");
  const [ttsLocale, setTtsLocale] = useState("en-IN");
  const [speakingRate, setSpeakingRate] = useState(1.0);
  const [outputSampleRate, setOutputSampleRate] = useState<number>(24000);
  const [targetAudioFormat, setTargetAudioFormat] = useState("mulaw");

  // System Prompt & Flow
  const [systemPrompt, setSystemPrompt] = useState("");
  const [initialNode, setInitialNode] = useState("greeting");
  const [nodes, setNodes] = useState<FlowNodeConfig[]>([]);

  // Knowledge & VAD
  const [attachedKBs, setAttachedKBs] = useState<string[]>([]);
  const [vectorWeight, setVectorWeight] = useState(0.7);
  const [keywordWeight, setKeywordWeight] = useState(0.3);
  const [topK, setTopK] = useState(4);

  // Audio & Limits
  const [maxDurationSecs, setMaxDurationSecs] = useState(300);
  const [idleTimeoutSecs, setIdleTimeoutSecs] = useState(60);
  const [vadConfidence, setVadConfidence] = useState(0.5);

  // Cadence: Classifier & Summarizer
  const [classifierEnabled, setClassifierEnabled] = useState(true);
  const [classifierPrompt, setClassifierPrompt] = useState(
    "Classify the supplied conversation using only observed evidence.",
  );
  const [classifierConfidence, setClassifierConfidence] = useState(0.8);
  const [classifierNodeExits, setClassifierNodeExits] = useState<string[]>([
    "discovery",
    "qualification",
  ]);

  const [summarizerEnabled, setSummarizerEnabled] = useState(false);
  const [summarizerPrompt, setSummarizerPrompt] = useState(
    "Summarize the supplied history faithfully; preserve decisions and facts.",
  );
  const [unsummarizedThreshold, setUnsummarizedThreshold] = useState(20);

  async function load() {
    if (!agentId) return;
    setLoading(true);
    setError("");
    try {
      const [versionsData, toolsData, kbData, agentData] = await Promise.all([
        api<{ versions: AgentVersionSummary[] }>(`/agents/${agentId}/versions`),
        api<{ tools: ToolItem[] }>("/tools").catch(() => ({ tools: [] })),
        api<{ knowledge_bases: KnowledgeBaseItem[] }>("/knowledge-bases").catch(() => ({
          knowledge_bases: [],
        })),
        api<{ agents: Array<{ id: string; name: string }> }>("/agents").catch(() => ({
          agents: [],
        })),
      ]);

      setAllVersions(versionsData.versions);
      setAvailableTools(toolsData.tools);
      setAvailableKBs(kbData.knowledge_bases);

      const ag = agentData.agents?.find((a) => a.id === agentId);
      if (ag) setAgentName(ag.name);

      const current = versionsData.versions.find((item) => item.id === versionId) ?? null;
      if (!current) {
        setError("Version not found for this agent.");
      } else {
        setVersion(current);
        const cfg = current.config;
        if (cfg.name) setAgentName(cfg.name);
        if (cfg.persona) setPersona(cfg.persona);
        setSystemPrompt(cfg.system_prompt || "");
        setNodes(cfg.flow?.nodes || []);
        setInitialNode(cfg.flow?.initial_node || "greeting");

        // Language config
        if (cfg.language?.default_language) setDefaultLang(cfg.language.default_language);
        if (cfg.language?.supported_languages) setSupportedLanguages(cfg.language.supported_languages);
        setFollowCallerLang(cfg.language?.follow_caller_language ?? true);
        setPersistLang(cfg.language?.persist_requested_language ?? true);

        // Providers
        if (cfg.stt?.model) setSttModel(cfg.stt.model);
        if (cfg.stt?.language) setSttLang(cfg.stt.language);

        if (cfg.llm?.provider) setLlmProvider(cfg.llm.provider as any);
        if (cfg.llm?.model) setLlmModel(cfg.llm.model);
        if (cfg.llm?.temperature !== undefined) setLlmTemp(cfg.llm.temperature);
        if (cfg.llm?.max_tokens !== undefined) setLlmMaxTokens(cfg.llm.max_tokens);

        if (cfg.tts?.provider) setTtsProvider(cfg.tts.provider as any);
        if (cfg.tts?.voice) setTtsVoice(cfg.tts.voice);
        if (cfg.tts?.language) setTtsLocale(cfg.tts.language);
        if (cfg.tts?.pace !== undefined) setSpeakingRate(cfg.tts.pace);

        // Limits & VAD
        if (cfg.call_limits?.max_duration_secs !== undefined) {
          setMaxDurationSecs(cfg.call_limits.max_duration_secs);
        }
        if (cfg.call_limits?.idle_timeout_secs !== undefined) {
          setIdleTimeoutSecs(cfg.call_limits.idle_timeout_secs);
        }
        if (cfg.vad?.confidence !== undefined) setVadConfidence(cfg.vad.confidence);

        // Knowledge & Retrieval
        if (cfg.knowledge_base_ids) setAttachedKBs(cfg.knowledge_base_ids);
        if (cfg.retrieval?.vector_weight !== undefined) setVectorWeight(cfg.retrieval.vector_weight);
        if (cfg.retrieval?.keyword_weight !== undefined) setKeywordWeight(cfg.retrieval.keyword_weight);
        if (cfg.retrieval?.top_k !== undefined) setTopK(cfg.retrieval.top_k);

        // Cadence
        if (cfg.classifier?.enabled !== undefined) setClassifierEnabled(cfg.classifier.enabled);
        if (cfg.classifier?.prompt) setClassifierPrompt(cfg.classifier.prompt);
        if (cfg.classifier?.confidence_threshold !== undefined) {
          setClassifierConfidence(cfg.classifier.confidence_threshold);
        }
        if (cfg.classifier?.node_exits) setClassifierNodeExits(cfg.classifier.node_exits);

        if (cfg.context?.summarizer?.enabled !== undefined) {
          setSummarizerEnabled(cfg.context.summarizer.enabled);
        }
        if (cfg.context?.summarizer?.prompt) {
          setSummarizerPrompt(cfg.context.summarizer.prompt);
        }
        if (cfg.context?.summarizer?.unsummarized_messages !== undefined) {
          setUnsummarizedThreshold(cfg.context.summarizer.unsummarized_messages);
        }

        setRevisionNote(current.note || "");
      }
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "Could not load version";
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
      name: agentName.trim(),
      persona: persona.trim(),
      system_prompt: systemPrompt.trim(),
      greeting: nodes.find((n) => n.id === initialNode)?.prompt || "",
      contact_variables: ["name", "phone_number"],
      language: {
        default_language: defaultLang,
        supported_languages: supportedLanguages,
        follow_caller_language: followCallerLang,
        persist_requested_language: persistLang,
      },
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
      tool_bindings: {},
      background_hooks: [],
      knowledge_base_ids: attachedKBs,
      retrieval: {
        top_k: Number(topK),
        vector_weight: Number(vectorWeight),
        keyword_weight: Number(keywordWeight),
        rerank_enabled: false,
      },
      stt: {
        provider: "sarvam",
        model: "saaras:v3",
      },
      llm: {
        provider: "groq",
        model: llmModel,
        temperature: Number(llmTemp),
        max_tokens: Number(llmMaxTokens),
      },
      tts: {
        provider: ttsProvider,
        voice: ttsVoice,
        language: ttsLocale,
        pace: Number(speakingRate),
        model: ttsProvider === "sarvam" ? "bulbul:v3" : "sonic-2",
      },
      vad: {
        confidence: Number(vadConfidence),
        start_secs: 0.1,
        stop_secs: 0.8,
        min_volume: 0.1,
      },
      audio: {
        sample_rate: sttSampleRate === 8000 ? 8000 : 16000,
        channels: 1,
        encoding: "pcm_s16le",
        frame_ms: 20,
      },
      call_limits: {
        max_duration_secs: Number(maxDurationSecs),
        idle_timeout_secs: Number(idleTimeoutSecs),
        interruptions_enabled: true,
      },
      context: {
        prune_node_ids: ["greeting"],
        remove_transition_tool_pairs: true,
        summarizer: {
          enabled: summarizerEnabled,
          prompt: summarizerPrompt.trim(),
          unsummarized_messages: Number(unsummarizedThreshold),
          context_window_tokens: 8192,
          compaction_threshold: 0.7,
          hard_ceiling: 0.9,
          target_ratio: 0.4,
          output_budget_tokens: 512,
          preserve_opening_messages: 2,
          preserve_recent_messages: 6,
        },
      },
      classifier: {
        enabled: classifierEnabled,
        node_exits: classifierNodeExits,
        prompt: classifierPrompt.trim(),
        confidence_threshold: Number(classifierConfidence),
        consecutive_verdicts: 1,
        answer_signals: [],
        topic_signals: [],
        keywords: [],
      },
      pipeline_logs: "inherit",
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
    if (!confirm("Are you sure you want to publish this draft? Published versions are immutable.")) {
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

  // Dynamic Flow Node Management
  function addNode() {
    const newId = `node_${nodes.length + 1}`;
    setNodes((prev) => [
      ...prev,
      {
        id: newId,
        prompt: "Describe what the agent should say and listen for at this step.",
        transitions: [],
        tool_bindings: [],
        respond_immediately: true,
        terminal: true,
      },
    ]);
    toast.info(`Added local node '${newId}'`);
  }

  function removeNode(index: number) {
    if (nodes.length <= 1) {
      toast.error("An agent flow must have at least one node.");
      return;
    }
    const removedId = nodes[index].id;
    const remaining = nodes.filter((_, i) => i !== index);
    const updated = remaining.map((n) => ({
      ...n,
      transitions: (n.transitions || []).filter((t) => t !== removedId),
    }));
    setNodes(updated);
    if (initialNode === removedId && updated.length > 0) {
      setInitialNode(updated[0].id);
    }
    toast.info(`Removed node '${removedId}'`);
  }

  function updateNode(index: number, updates: Partial<FlowNodeConfig>) {
    setNodes((prev) => {
      const updated = [...prev];
      updated[index] = { ...updated[index], ...updates };
      return updated;
    });
  }

  function toggleNodeTransition(nodeIndex: number, targetNodeId: string) {
    const node = nodes[nodeIndex];
    const currentTransitions = node.transitions || [];
    const updatedTransitions = currentTransitions.includes(targetNodeId)
      ? currentTransitions.filter((t) => t !== targetNodeId)
      : [...currentTransitions, targetNodeId];
    updateNode(nodeIndex, { transitions: updatedTransitions });
  }

  function toggleNodeTool(nodeIndex: number, toolName: string) {
    const node = nodes[nodeIndex];
    const currentTools = node.tool_bindings || [];
    const updatedTools = currentTools.includes(toolName)
      ? currentTools.filter((t) => t !== toolName)
      : [...currentTools, toolName];
    updateNode(nodeIndex, { tool_bindings: updatedTools });
  }

  if (loading) {
    return (
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-4 p-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (!version) {
    return (
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-4 p-6">
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
  const allCurrentNodeIds = nodes.map((n) => n.id);

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-5 p-6">
      {/* Top Breadcrumb & Header matching Image 3 */}
      <div>
        <div className="mb-2 flex items-center gap-1.5 text-xs text-muted-foreground">
          <Link to="/agents" className="hover:text-foreground transition-colors">
            Agents
          </Link>
          <span>&gt;</span>
          <span className="text-foreground font-medium">{agentName}</span>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-4 mt-2">
          {/* Left: Bot avatar & title */}
          <div className="flex items-center gap-3.5">
            <div className="flex size-11 items-center justify-center rounded-full bg-blue-50 text-blue-600 border border-blue-200">
              <Bot className="size-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  disabled={!isDraft}
                  value={agentName}
                  onChange={(e) => setAgentName(e.target.value)}
                  className="text-xl font-bold tracking-tight bg-transparent border-b border-transparent hover:border-border focus:border-primary focus:outline-none px-1 -mx-1"
                />
                <Badge
                  variant="outline"
                  className={
                    isDraft
                      ? "bg-amber-50 text-amber-700 border-amber-200 text-xs font-normal"
                      : "bg-emerald-50 text-emerald-700 border-emerald-200 text-xs font-normal"
                  }
                >
                  {isDraft ? "Draft" : "Published"}
                </Badge>
              </div>
              <input
                type="text"
                disabled={!isDraft}
                value={persona}
                onChange={(e) => setPersona(e.target.value)}
                placeholder="Voice agent description and intent..."
                className="text-xs text-muted-foreground mt-0.5 bg-transparent border-b border-transparent hover:border-border focus:border-primary focus:outline-none w-full max-w-md px-1 -mx-1"
              />
            </div>
          </div>

          {/* Right: Version Selector & Actions */}
          <div className="flex items-center gap-2.5">
            <div className="flex flex-col items-end">
              <span className="text-[10px] text-muted-foreground uppercase font-mono">
                Version
              </span>
              <NativeSelect
                value={version.id}
                onChange={(e) => navigate(`/agents/${agentId}/versions/${e.target.value}`)}
                className="h-8 text-xs font-mono w-36"
              >
                {allVersions.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.version} ({v.status === "draft" ? "latest draft" : "published"})
                  </option>
                ))}
              </NativeSelect>
            </div>

            {isDraft ? (
              <>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={saving}
                  onClick={() => void handleSaveDraft()}
                  className="gap-1.5"
                >
                  <Save className="size-4" />
                  {saving ? "Saving…" : "Save draft"}
                </Button>
                <Button
                  size="sm"
                  disabled={publishing}
                  onClick={() => void handlePublish()}
                  className="gap-1.5 bg-blue-600 hover:bg-blue-700 text-white"
                >
                  <Send className="size-4" />
                  {publishing ? "Publishing…" : "Publish"}
                </Button>
              </>
            ) : (
              <Button size="sm" variant="outline" onClick={() => void handleCloneDraft()}>
                <Copy className="size-3.5 mr-1.5" /> Clone as New Draft
              </Button>
            )}
          </div>
        </div>
      </div>

      {!isDraft && (
        <div className="flex items-center gap-2 rounded-md border border-amber-200 bg-amber-50/50 p-3 text-xs text-amber-900">
          <Lock className="size-4 shrink-0 text-amber-600" />
          <span>
            This published version is immutable and locked for modifications. Click <strong>Clone as New Draft</strong> to branch a new version.
          </span>
        </div>
      )}

      {/* Tabs Layout matching Image 3 */}
      <Tabs defaultValue="runtime" className="w-full">
        <TabsList className="flex flex-wrap w-full justify-start border-b rounded-none bg-transparent p-0 h-auto gap-4">
          <TabsTrigger
            value="runtime"
            className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent px-3 py-2 text-xs font-medium"
          >
            Runtime
          </TabsTrigger>
          <TabsTrigger
            value="models"
            className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent px-3 py-2 text-xs font-medium"
          >
            Model & Prompts
          </TabsTrigger>
          <TabsTrigger
            value="flow"
            className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent px-3 py-2 text-xs font-medium"
          >
            Flow Graph
          </TabsTrigger>
          <TabsTrigger
            value="tools"
            className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent px-3 py-2 text-xs font-medium"
          >
            Tools
          </TabsTrigger>
          <TabsTrigger
            value="knowledge"
            className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent px-3 py-2 text-xs font-medium"
          >
            Knowledge
          </TabsTrigger>
          <TabsTrigger
            value="voice"
            className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent px-3 py-2 text-xs font-medium"
          >
            Voice & Audio
          </TabsTrigger>
          <TabsTrigger
            value="cadence"
            className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent px-3 py-2 text-xs font-medium"
          >
            Cadence & Evaluation
          </TabsTrigger>
        </TabsList>

        {/* Tab 1: Runtime (Runtime Mode Cards matching Image 3 + Multilingual) */}
        <TabsContent value="runtime" className="flex flex-col gap-5 pt-4">
          {/* Runtime Mode Selector */}
          <section className="flex flex-col gap-2.5">
            <div>
              <h3 className="text-sm font-semibold text-foreground">Runtime mode</h3>
              <p className="text-xs text-muted-foreground">
                Choose how this agent processes voice calls.
              </p>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {/* Cascaded */}
              <div
                onClick={() => isDraft && setRuntimeMode("cascaded")}
                className={`flex items-start justify-between p-4 rounded-lg border cursor-pointer transition-all ${
                  runtimeMode === "cascaded"
                    ? "border-blue-500 bg-blue-50/20 ring-1 ring-blue-500"
                    : "border-border hover:border-muted-foreground/40 bg-card"
                }`}
              >
                <div className="flex items-start gap-3">
                  <div className="flex size-8 items-center justify-center rounded bg-blue-100/50 text-blue-600">
                    <Cpu className="size-4" />
                  </div>
                  <div>
                    <h4 className="text-xs font-semibold">Cascaded</h4>
                    <p className="text-[11px] text-muted-foreground mt-0.5">
                      Modular pipeline with separate STT → LLM → TTS stages.
                    </p>
                  </div>
                </div>
                <div
                  className={`size-4 rounded-full border flex items-center justify-center ${
                    runtimeMode === "cascaded"
                      ? "border-blue-600 bg-blue-600"
                      : "border-muted-foreground/40"
                  }`}
                >
                  {runtimeMode === "cascaded" && <div className="size-1.5 rounded-full bg-white" />}
                </div>
              </div>

              {/* Speech to Speech */}
              <div
                onClick={() => isDraft && setRuntimeMode("s2s")}
                className={`flex items-start justify-between p-4 rounded-lg border cursor-pointer transition-all ${
                  runtimeMode === "s2s"
                    ? "border-blue-500 bg-blue-50/20 ring-1 ring-blue-500"
                    : "border-border hover:border-muted-foreground/40 bg-card"
                }`}
              >
                <div className="flex items-start gap-3">
                  <div className="flex size-8 items-center justify-center rounded bg-blue-100/50 text-blue-600">
                    <Volume2 className="size-4" />
                  </div>
                  <div>
                    <h4 className="text-xs font-semibold">Speech-to-speech</h4>
                    <p className="text-[11px] text-muted-foreground mt-0.5">
                      End-to-end voice model for natural conversations.
                    </p>
                  </div>
                </div>
                <div
                  className={`size-4 rounded-full border flex items-center justify-center ${
                    runtimeMode === "s2s"
                      ? "border-blue-600 bg-blue-600"
                      : "border-muted-foreground/40"
                  }`}
                >
                  {runtimeMode === "s2s" && <div className="size-1.5 rounded-full bg-white" />}
                </div>
              </div>

              {/* Pipecat (recommended) */}
              <div
                onClick={() => isDraft && setRuntimeMode("pipecat")}
                className={`flex items-start justify-between p-4 rounded-lg border cursor-pointer transition-all ${
                  runtimeMode === "pipecat"
                    ? "border-blue-500 bg-blue-50/20 ring-1 ring-blue-500"
                    : "border-border hover:border-muted-foreground/40 bg-card"
                }`}
              >
                <div className="flex items-start gap-3">
                  <div className="flex size-8 items-center justify-center rounded bg-blue-100/50 text-blue-600">
                    <Layers className="size-4" />
                  </div>
                  <div>
                    <h4 className="text-xs font-semibold">Pipecat</h4>
                    <p className="text-[11px] text-muted-foreground mt-0.5">
                      Low-latency, highly configurable voice pipeline (recommended).
                    </p>
                  </div>
                </div>
                <div
                  className={`size-4 rounded-full border flex items-center justify-center ${
                    runtimeMode === "pipecat"
                      ? "border-blue-600 bg-blue-600"
                      : "border-muted-foreground/40"
                  }`}
                >
                  {runtimeMode === "pipecat" && <div className="size-1.5 rounded-full bg-white" />}
                </div>
              </div>
            </div>
          </section>

          {/* Multilingual & Language Registry Island */}
          <Card className="shadow-none">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-semibold">Language & Dialect Configuration</CardTitle>
              <CardDescription className="text-xs">
                Configure primary agent language and active regional dialect registers (Telugu, Marathi, Hindi, English).
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <Field>
                  <FieldLabel htmlFor="def-lang">Default Primary Language</FieldLabel>
                  <NativeSelect
                    id="def-lang"
                    disabled={!isDraft}
                    value={defaultLang}
                    onChange={(e) => setDefaultLang(e.target.value)}
                  >
                    <option value="en-IN">English (India) · en-IN</option>
                    <option value="te-IN">Telugu (India) · te-IN</option>
                    <option value="mr-IN">Marathi (India) · mr-IN</option>
                    <option value="hi-IN">Hindi (India) · hi-IN</option>
                  </NativeSelect>
                </Field>

                <Field>
                  <FieldLabel>Active Language Registers</FieldLabel>
                  <div className="flex flex-wrap gap-2 pt-1">
                    {[
                      { code: "te-IN", label: "Telugu (te-IN)" },
                      { code: "mr-IN", label: "Marathi (mr-IN)" },
                      { code: "hi-IN", label: "Hindi (hi-IN)" },
                      { code: "en-IN", label: "English (en-IN)" },
                    ].map((item) => {
                      const active = supportedLanguages.includes(item.code);
                      return (
                        <Badge
                          key={item.code}
                          variant="outline"
                          onClick={() => {
                            if (!isDraft) return;
                            setSupportedLanguages((prev) =>
                              active
                                ? prev.filter((c) => c !== item.code)
                                : [...prev, item.code],
                            );
                          }}
                          className={`cursor-pointer text-xs py-1 px-2.5 transition-colors ${
                            active
                              ? "bg-blue-50 text-blue-700 border-blue-300 font-medium"
                              : "text-muted-foreground opacity-60 hover:opacity-100"
                          }`}
                        >
                          {active && <Check className="size-3 mr-1" />}
                          {item.label}
                        </Badge>
                      );
                    })}
                  </div>
                </Field>
              </div>

              <div className="flex flex-wrap items-center gap-6 pt-2 border-t">
                <div className="flex items-center gap-2">
                  <input
                    id="follow-caller"
                    type="checkbox"
                    disabled={!isDraft}
                    checked={followCallerLang}
                    onChange={(e) => setFollowCallerLang(e.target.checked)}
                    className="size-4 rounded border-gray-300 text-primary"
                  />
                  <label htmlFor="follow-caller" className="text-xs text-foreground cursor-pointer">
                    Follow caller language dynamically mid-call
                  </label>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    id="persist-lang"
                    type="checkbox"
                    disabled={!isDraft}
                    checked={persistLang}
                    onChange={(e) => setPersistLang(e.target.checked)}
                    className="size-4 rounded border-gray-300 text-primary"
                  />
                  <label htmlFor="persist-lang" className="text-xs text-foreground cursor-pointer">
                    Persist caller's preferred language in contact record
                  </label>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Tab 2: Model & Prompts (Exact 3-Island Layout from Image 2) */}
        <TabsContent value="models" className="flex flex-col gap-5 pt-4">
          <section className="rounded-lg border bg-card p-5 shadow-xs">
            <div className="mb-4">
              <h3 className="text-sm font-semibold text-foreground">
                Pipeline Configuration
              </h3>
              <p className="mt-0.5 text-xs text-muted-foreground">
                Configure speech recognition, language intelligence, and text-to-speech options.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 md:divide-x divide-border/60">
              {/* Island 1: Speech to Text (STT) */}
              <div className="flex flex-col gap-4">
                <div className="flex items-center gap-2 pb-1 border-b border-border/40">
                  <span className="flex size-7 items-center justify-center rounded-md bg-blue-50 text-blue-600">
                    <AudioLines className="size-4" />
                  </span>
                  <div>
                    <h4 className="text-xs font-semibold text-foreground">
                      Speech to Text (STT)
                    </h4>
                    <p className="text-[11px] text-muted-foreground">
                      Convert caller audio to text
                    </p>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <Field>
                    <FieldLabel htmlFor="stt-prov">Provider</FieldLabel>
                    <NativeSelect
                      id="stt-prov"
                      disabled={!isDraft}
                      value={sttProvider}
                      onChange={(e) => setSttProvider(e.target.value as any)}
                    >
                      <option value="sarvam">sarvam</option>
                      <option value="deepgram">deepgram</option>
                    </NativeSelect>
                  </Field>

                  <Field>
                    <FieldLabel htmlFor="stt-model">Model</FieldLabel>
                    <NativeSelect
                      id="stt-model"
                      disabled={!isDraft}
                      value={sttModel}
                      onChange={(e) => setSttModel(e.target.value)}
                    >
                      <option value="saaras:v3">saaras:v3-realtime</option>
                      <option value="nova-3">nova-3</option>
                    </NativeSelect>
                  </Field>
                </div>

                <Field>
                  <FieldLabel htmlFor="stt-lang">Language</FieldLabel>
                  <NativeSelect
                    id="stt-lang"
                    disabled={!isDraft}
                    value={sttLang}
                    onChange={(e) => setSttLang(e.target.value)}
                  >
                    <option value="te">te (Telugu)</option>
                    <option value="en">en (English)</option>
                    <option value="mr">mr (Marathi)</option>
                    <option value="hi">hi (Hindi)</option>
                  </NativeSelect>
                </Field>

                <Field>
                  <FieldLabel htmlFor="stt-rate">Input sample rate</FieldLabel>
                  <NativeSelect
                    id="stt-rate"
                    disabled={!isDraft}
                    value={sttSampleRate}
                    onChange={(e) => setSttSampleRate(Number(e.target.value))}
                  >
                    <option value="8000">8000 Hz (telephony)</option>
                    <option value="16000">16000 Hz (wideband)</option>
                  </NativeSelect>
                </Field>

                <div className="flex flex-col gap-1.5">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-medium text-muted-foreground">
                      Endpointing sensitivity
                    </span>
                    <span className="w-12 text-center text-xs font-mono font-medium rounded border py-0.5 bg-background">
                      {sttSensitivity.toFixed(1)}
                    </span>
                  </div>
                  <input
                    type="range"
                    disabled={!isDraft}
                    min="0"
                    max="1"
                    step="0.05"
                    value={sttSensitivity}
                    onChange={(e) => setSttSensitivity(parseFloat(e.target.value))}
                    className="h-1.5 w-full cursor-pointer appearance-none rounded-lg bg-muted accent-primary"
                  />
                </div>

                <div className="flex items-center justify-between gap-2 pt-1">
                  <div className="flex flex-col">
                    <span className="text-xs font-medium text-foreground">
                      Partial transcripts
                    </span>
                    <span className="text-[11px] text-muted-foreground">
                      Stream interim transcripts during speech
                    </span>
                  </div>
                  <input
                    type="checkbox"
                    disabled={!isDraft}
                    checked={partialTranscripts}
                    onChange={(e) => setPartialTranscripts(e.target.checked)}
                    className="size-4 rounded border-gray-300 text-primary"
                  />
                </div>
              </div>

              {/* Island 2: Language Model (LLM) */}
              <div className="flex flex-col gap-4 md:pl-6">
                <div className="flex items-center gap-2 pb-1 border-b border-border/40">
                  <span className="flex size-7 items-center justify-center rounded-md bg-blue-50 text-blue-600">
                    <Brain className="size-4" />
                  </span>
                  <div>
                    <h4 className="text-xs font-semibold text-foreground">
                      Language Model (LLM)
                    </h4>
                    <p className="text-[11px] text-muted-foreground">
                      Generate intelligent responses
                    </p>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <Field>
                    <FieldLabel htmlFor="llm-prov">Provider</FieldLabel>
                    <NativeSelect
                      id="llm-prov"
                      disabled={!isDraft}
                      value={llmProvider}
                      onChange={(e) => setLlmProvider(e.target.value as any)}
                    >
                      <option value="groq">groq</option>
                      <option value="google">gemini</option>
                    </NativeSelect>
                  </Field>

                  <Field>
                    <FieldLabel htmlFor="llm-mod">Model</FieldLabel>
                    <NativeSelect
                      id="llm-mod"
                      disabled={!isDraft}
                      value={llmModel}
                      onChange={(e) => setLlmModel(e.target.value)}
                    >
                      <option value="llama-3.3-70b-versatile">llama-3.3-70b-versatile</option>
                      <option value="qwen/qwen3.8-27b">qwen/qwen3.8-27b</option>
                      <option value="gemini-2.5-flash">gemini-2.5-flash</option>
                      <option value="gemini-3.5-flash-lite">gemini-3.5-flash-lite</option>
                      <option value="llama-3.1-8b-instant">llama-3.1-8b-instant</option>
                    </NativeSelect>
                  </Field>
                </div>

                <div className="grid grid-cols-2 gap-3 items-end">
                  <div className="flex flex-col gap-1.5 flex-1 min-w-0">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-medium text-muted-foreground">
                        Temperature
                      </span>
                      <span className="w-12 text-center text-xs font-mono font-medium rounded border py-0.5 bg-background">
                        {llmTemp.toFixed(1)}
                      </span>
                    </div>
                    <input
                      type="range"
                      disabled={!isDraft}
                      min="0"
                      max="2"
                      step="0.1"
                      value={llmTemp}
                      onChange={(e) => setLlmTemp(parseFloat(e.target.value))}
                      className="h-1.5 w-full cursor-pointer appearance-none rounded-lg bg-muted accent-primary"
                    />
                  </div>

                  <Field>
                    <FieldLabel htmlFor="llm-max">Max tokens</FieldLabel>
                    <Input
                      id="llm-max"
                      type="number"
                      disabled={!isDraft}
                      className="h-8 text-xs font-mono"
                      value={llmMaxTokens}
                      onChange={(e) => setLlmMaxTokens(Number(e.target.value))}
                    />
                  </Field>
                </div>

                <div className="flex items-center justify-between gap-2 pt-2">
                  <div className="flex flex-col">
                    <span className="text-xs font-medium text-foreground">
                      Enable tool calling
                    </span>
                    <span className="text-[11px] text-muted-foreground">
                      Allow the model to use tools and functions
                    </span>
                  </div>
                  <input
                    type="checkbox"
                    disabled={!isDraft}
                    checked={enableToolCalling}
                    onChange={(e) => setEnableToolCalling(e.target.checked)}
                    className="size-4 rounded border-gray-300 text-primary"
                  />
                </div>
              </div>

              {/* Island 3: Text to Speech (TTS) */}
              <div className="flex flex-col gap-4 md:pl-6">
                <div className="flex items-center gap-2 pb-1 border-b border-border/40">
                  <span className="flex size-7 items-center justify-center rounded-md bg-blue-50 text-blue-600">
                    <Volume2 className="size-4" />
                  </span>
                  <div>
                    <h4 className="text-xs font-semibold text-foreground">
                      Text to Speech (TTS)
                    </h4>
                    <p className="text-[11px] text-muted-foreground">
                      Convert text to natural speech
                    </p>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <Field>
                    <FieldLabel htmlFor="tts-prov">Provider</FieldLabel>
                    <NativeSelect
                      id="tts-prov"
                      disabled={!isDraft}
                      value={ttsProvider}
                      onChange={(e) => setTtsProvider(e.target.value as any)}
                    >
                      <option value="sarvam">sarvam</option>
                      <option value="cartesia">cartesia</option>
                    </NativeSelect>
                  </Field>

                  <Field>
                    <FieldLabel htmlFor="tts-voice">Voice</FieldLabel>
                    <NativeSelect
                      id="tts-voice"
                      disabled={!isDraft}
                      value={ttsVoice}
                      onChange={(e) => setTtsVoice(e.target.value)}
                    >
                      <option value="ritu">ritu (Indic)</option>
                      <option value="bulbul:v3">bulbul:v3</option>
                      <option value="sonic-english">sonic-english</option>
                      <option value="sonic-multilingual">sonic-multilingual</option>
                    </NativeSelect>
                  </Field>
                </div>

                <Field>
                  <FieldLabel htmlFor="tts-locale">Language / locale</FieldLabel>
                  <NativeSelect
                    id="tts-locale"
                    disabled={!isDraft}
                    value={ttsLocale}
                    onChange={(e) => setTtsLocale(e.target.value)}
                  >
                    <option value="te-IN">te-IN (Telugu)</option>
                    <option value="en-IN">en-IN (English India)</option>
                    <option value="en-US">en-US (English US)</option>
                    <option value="hi-IN">hi-IN (Hindi)</option>
                    <option value="mr-IN">mr-IN (Marathi)</option>
                  </NativeSelect>
                </Field>

                <div className="flex flex-col gap-1.5">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-medium text-muted-foreground">
                      Speaking rate
                    </span>
                    <span className="w-12 text-center text-xs font-mono font-medium rounded border py-0.5 bg-background">
                      {speakingRate.toFixed(1)}
                    </span>
                  </div>
                  <input
                    type="range"
                    disabled={!isDraft}
                    min="0.5"
                    max="2.0"
                    step="0.1"
                    value={speakingRate}
                    onChange={(e) => setSpeakingRate(parseFloat(e.target.value))}
                    className="h-1.5 w-full cursor-pointer appearance-none rounded-lg bg-muted accent-primary"
                  />
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <Field>
                    <FieldLabel htmlFor="tts-out-rate">Output sample rate</FieldLabel>
                    <NativeSelect
                      id="tts-out-rate"
                      disabled={!isDraft}
                      value={outputSampleRate}
                      onChange={(e) => setOutputSampleRate(Number(e.target.value))}
                    >
                      <option value="24000">24000 Hz</option>
                      <option value="16000">16000 Hz</option>
                      <option value="8000">8000 Hz</option>
                    </NativeSelect>
                  </Field>

                  <Field>
                    <FieldLabel htmlFor="tts-format">Target audio format</FieldLabel>
                    <NativeSelect
                      id="tts-format"
                      disabled={!isDraft}
                      value={targetAudioFormat}
                      onChange={(e) => setTargetAudioFormat(e.target.value)}
                    >
                      <option value="mulaw">mulaw (8 kHz, PSTN)</option>
                      <option value="pcm">pcm (16-bit)</option>
                    </NativeSelect>
                  </Field>
                </div>
              </div>
            </div>
          </section>

          {/* System Prompt */}
          <Card className="shadow-none">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">Global System Instructions</CardTitle>
              <CardDescription className="text-xs">
                Master instructions governing conversation guidelines, voice persona, and safety boundaries.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <Textarea
                rows={6}
                disabled={!isDraft}
                placeholder="You are an empathetic, articulate assistant..."
                className="font-sans text-xs"
                value={systemPrompt}
                onChange={(e) => setSystemPrompt(e.target.value)}
              />
              <Field>
                <FieldLabel htmlFor="rev-note">Revision Changelog Note</FieldLabel>
                <Input
                  id="rev-note"
                  disabled={!isDraft}
                  placeholder="e.g. Added Telugu language support and updated prompt cadence"
                  className="text-xs"
                  value={revisionNote}
                  onChange={(e) => setRevisionNote(e.target.value)}
                />
              </Field>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Tab 3: Flow Graph (Dynamic Transition Dropdowns + Per-Node Tools) */}
        <TabsContent value="flow" className="flex flex-col gap-5 pt-4">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <span className="text-xs font-medium text-muted-foreground">Initial Entry Node:</span>
              <NativeSelect
                value={initialNode}
                disabled={!isDraft}
                onChange={(e) => setInitialNode(e.target.value)}
                className="h-8 text-xs font-mono w-48"
              >
                {allCurrentNodeIds.map((nId) => (
                  <option key={nId} value={nId}>
                    {nId}
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
                        className="h-7 text-xs font-mono font-semibold w-44"
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
                <CardContent className="p-4 pt-0 flex flex-col gap-3.5">
                  <Field>
                    <FieldLabel htmlFor={`prompt-${idx}`} className="text-xs">
                      Node Prompt & Conversation Directive
                    </FieldLabel>
                    <Textarea
                      id={`prompt-${idx}`}
                      rows={3}
                      disabled={!isDraft}
                      placeholder="Instruct what the agent should say and listen for at this step..."
                      className="text-xs font-sans"
                      value={node.prompt}
                      onChange={(e) => updateNode(idx, { prompt: e.target.value })}
                    />
                  </Field>

                  {/* Allowed Transitions: Visual Dynamic Checkbox/Badge Selector */}
                  <div>
                    <span className="text-[11px] font-medium text-muted-foreground block mb-1.5">
                      Allowed Outgoing Transitions (select reachable nodes):
                    </span>
                    <div className="flex flex-wrap items-center gap-1.5 p-2 rounded-md border bg-muted/20">
                      {allCurrentNodeIds
                        .filter((nId) => nId !== node.id)
                        .map((targetId) => {
                          const isTransition = (node.transitions || []).includes(targetId);
                          return (
                            <Badge
                              key={targetId}
                              variant="outline"
                              onClick={() => isDraft && toggleNodeTransition(idx, targetId)}
                              className={`cursor-pointer font-mono text-[11px] py-0.5 px-2 transition-colors ${
                                isTransition
                                  ? "bg-blue-50 text-blue-700 border-blue-300 font-semibold"
                                  : "bg-background text-muted-foreground opacity-60 hover:opacity-100"
                              }`}
                            >
                              {isTransition && <Check className="size-3 mr-1" />}
                              → {targetId}
                            </Badge>
                          );
                        })}
                      {allCurrentNodeIds.length <= 1 && (
                        <span className="text-[11px] text-muted-foreground italic">
                          Add another node to enable transitions.
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Per-Node Tool Additions */}
                  <div>
                    <span className="text-[11px] font-medium text-muted-foreground block mb-1.5">
                      Active Tools for this Node:
                    </span>
                    <div className="flex flex-wrap items-center gap-1.5 p-2 rounded-md border bg-muted/20">
                      {availableTools.length === 0 ? (
                        <span className="text-[11px] text-muted-foreground italic">
                          No registered tools found. Register tools in the Tools page.
                        </span>
                      ) : (
                        availableTools.map((t) => {
                          const isAttached = (node.tool_bindings || []).includes(t.name);
                          return (
                            <Badge
                              key={t.id}
                              variant="outline"
                              onClick={() => isDraft && toggleNodeTool(idx, t.name)}
                              className={`cursor-pointer font-mono text-[11px] py-0.5 px-2 transition-colors ${
                                isAttached
                                  ? "bg-emerald-50 text-emerald-700 border-emerald-300 font-semibold"
                                  : "bg-background text-muted-foreground opacity-60 hover:opacity-100"
                              }`}
                            >
                              <Wrench className="size-3 mr-1" />
                              {t.name}
                            </Badge>
                          );
                        })
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-2 pt-1">
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
                    <label htmlFor={`resp-imm-${idx}`} className="text-xs text-muted-foreground cursor-pointer">
                      Speak immediately upon node entry
                    </label>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        {/* Tab 4: Tools (Global Tool Configuration) */}
        <TabsContent value="tools" className="flex flex-col gap-4 pt-4">
          <Card className="shadow-none">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">Global Tool Registry</CardTitle>
              <CardDescription className="text-xs">
                All registered tools available in this workspace that can be bound to nodes.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              {availableTools.length === 0 ? (
                <Empty>
                  <EmptyHeader>
                    <EmptyTitle>No tools configured</EmptyTitle>
                    <EmptyDescription>Create or seed tools in the Tools tab.</EmptyDescription>
                  </EmptyHeader>
                </Empty>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {availableTools.map((t) => (
                    <div key={t.id} className="p-3 border rounded-lg bg-muted/10 flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Wrench className="size-4 text-emerald-600" />
                        <div>
                          <span className="text-xs font-semibold font-mono">{t.name}</span>
                          <span className="text-[11px] text-muted-foreground block">ID: {t.id.slice(0, 8)}…</span>
                        </div>
                      </div>
                      <Badge variant="outline" className="text-[10px]">Ready</Badge>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Tab 5: Knowledge (RAG Attachment) */}
        <TabsContent value="knowledge" className="flex flex-col gap-4 pt-4">
          <Card className="shadow-none">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">Knowledge Bases (pgvector)</CardTitle>
              <CardDescription className="text-xs">
                Attach vector document collections to supply grounded RAG context during calls.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <div className="flex flex-col gap-2">
                <span className="text-xs font-medium text-muted-foreground">Select attached knowledge collections:</span>
                <div className="flex flex-wrap gap-2">
                  {availableKBs.map((kb) => {
                    const isAttached = attachedKBs.includes(kb.id);
                    return (
                      <Badge
                        key={kb.id}
                        variant="outline"
                        onClick={() => {
                          if (!isDraft) return;
                          setAttachedKBs((prev) =>
                            isAttached ? prev.filter((id) => id !== kb.id) : [...prev, kb.id],
                          );
                        }}
                        className={`cursor-pointer py-1 px-3 text-xs transition-colors ${
                          isAttached
                            ? "bg-blue-50 text-blue-700 border-blue-300 font-semibold"
                            : "opacity-60 hover:opacity-100"
                        }`}
                      >
                        <Database className="size-3.5 mr-1.5" />
                        {kb.name}
                      </Badge>
                    );
                  })}
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-3 border-t">
                <Field>
                  <FieldLabel>Vector Weight ({vectorWeight})</FieldLabel>
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.05"
                    disabled={!isDraft}
                    value={vectorWeight}
                    onChange={(e) => setVectorWeight(parseFloat(e.target.value))}
                    className="h-1.5 w-full cursor-pointer accent-primary"
                  />
                </Field>

                <Field>
                  <FieldLabel>Keyword Weight ({keywordWeight})</FieldLabel>
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.05"
                    disabled={!isDraft}
                    value={keywordWeight}
                    onChange={(e) => setKeywordWeight(parseFloat(e.target.value))}
                    className="h-1.5 w-full cursor-pointer accent-primary"
                  />
                </Field>

                <Field>
                  <FieldLabel>Top-K Retrieval Chunks</FieldLabel>
                  <Input
                    type="number"
                    min={1}
                    max={10}
                    disabled={!isDraft}
                    value={topK}
                    onChange={(e) => setTopK(Number(e.target.value))}
                  />
                </Field>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Tab 6: Voice & Audio (VAD & Call Limits) */}
        <TabsContent value="voice" className="flex flex-col gap-4 pt-4">
          <Card className="shadow-none">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">Voice Activity Detection (VAD) & Limits</CardTitle>
              <CardDescription className="text-xs">
                Fine-tune speech interruption detection, silence thresholds, and maximum call length.
              </CardDescription>
            </CardHeader>
            <CardContent className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <Field>
                <FieldLabel>Silero VAD Confidence ({vadConfidence})</FieldLabel>
                <input
                  type="range"
                  min="0.1"
                  max="0.9"
                  step="0.05"
                  disabled={!isDraft}
                  value={vadConfidence}
                  onChange={(e) => setVadConfidence(parseFloat(e.target.value))}
                  className="h-1.5 w-full cursor-pointer accent-primary"
                />
              </Field>

              <Field>
                <FieldLabel htmlFor="max-dur">Max Call Duration (seconds)</FieldLabel>
                <Input
                  id="max-dur"
                  type="number"
                  min={30}
                  max={3600}
                  disabled={!isDraft}
                  value={maxDurationSecs}
                  onChange={(e) => setMaxDurationSecs(Number(e.target.value))}
                />
              </Field>

              <Field>
                <FieldLabel htmlFor="idle-dur">Silence Timeout (seconds)</FieldLabel>
                <Input
                  id="idle-dur"
                  type="number"
                  min={10}
                  max={300}
                  disabled={!isDraft}
                  value={idleTimeoutSecs}
                  onChange={(e) => setIdleTimeoutSecs(Number(e.target.value))}
                />
              </Field>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Tab 7: Cadence & Evaluation (Classifier & Summarizer) */}
        <TabsContent value="cadence" className="flex flex-col gap-5 pt-4">
          {/* Classifier Cadence */}
          <Card className="shadow-none">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-sm font-semibold">Intent Classifier Cadence</CardTitle>
                  <CardDescription className="text-xs">
                    Autonomous background LLM inference to classify buyer interest, qualification, and stage.
                  </CardDescription>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    id="clf-en"
                    type="checkbox"
                    disabled={!isDraft}
                    checked={classifierEnabled}
                    onChange={(e) => setClassifierEnabled(e.target.checked)}
                    className="size-4 rounded border-gray-300 text-primary"
                  />
                  <label htmlFor="clf-en" className="text-xs font-medium cursor-pointer">
                    Enabled
                  </label>
                </div>
              </div>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <Field>
                <FieldLabel htmlFor="clf-prompt">Classifier Prompt Directive</FieldLabel>
                <Textarea
                  id="clf-prompt"
                  rows={3}
                  disabled={!isDraft || !classifierEnabled}
                  value={classifierPrompt}
                  onChange={(e) => setClassifierPrompt(e.target.value)}
                  className="text-xs font-sans"
                />
              </Field>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <Field>
                  <FieldLabel>Confidence Threshold ({classifierConfidence})</FieldLabel>
                  <input
                    type="range"
                    min="0.5"
                    max="1.0"
                    step="0.05"
                    disabled={!isDraft || !classifierEnabled}
                    value={classifierConfidence}
                    onChange={(e) => setClassifierConfidence(parseFloat(e.target.value))}
                    className="h-1.5 w-full cursor-pointer accent-primary"
                  />
                </Field>

                <Field>
                  <FieldLabel>Trigger On Node Exits</FieldLabel>
                  <div className="flex flex-wrap gap-1.5 pt-1">
                    {allCurrentNodeIds.map((nId) => {
                      const active = classifierNodeExits.includes(nId);
                      return (
                        <Badge
                          key={nId}
                          variant="outline"
                          onClick={() => {
                            if (!isDraft || !classifierEnabled) return;
                            setClassifierNodeExits((prev) =>
                              active ? prev.filter((id) => id !== nId) : [...prev, nId],
                            );
                          }}
                          className={`cursor-pointer font-mono text-[11px] ${
                            active
                              ? "bg-blue-50 text-blue-700 border-blue-300"
                              : "opacity-60 hover:opacity-100"
                          }`}
                        >
                          {nId}
                        </Badge>
                      );
                    })}
                  </div>
                </Field>
              </div>
            </CardContent>
          </Card>

          {/* Context Summarizer Cadence */}
          <Card className="shadow-none">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-sm font-semibold">Context History Summarizer</CardTitle>
                  <CardDescription className="text-xs">
                    Periodically compress lengthy call transcript history to keep LLM context crisp and responsive.
                  </CardDescription>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    id="sum-en"
                    type="checkbox"
                    disabled={!isDraft}
                    checked={summarizerEnabled}
                    onChange={(e) => setSummarizerEnabled(e.target.checked)}
                    className="size-4 rounded border-gray-300 text-primary"
                  />
                  <label htmlFor="sum-en" className="text-xs font-medium cursor-pointer">
                    Enabled
                  </label>
                </div>
              </div>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <Field>
                <FieldLabel htmlFor="sum-prompt">Summarizer Prompt Directive</FieldLabel>
                <Textarea
                  id="sum-prompt"
                  rows={2}
                  disabled={!isDraft || !summarizerEnabled}
                  value={summarizerPrompt}
                  onChange={(e) => setSummarizerPrompt(e.target.value)}
                  className="text-xs font-sans"
                />
              </Field>

              <Field>
                <FieldLabel htmlFor="sum-thresh">Unsummarized Exchanges Trigger</FieldLabel>
                <Input
                  id="sum-thresh"
                  type="number"
                  min={5}
                  max={50}
                  disabled={!isDraft || !summarizerEnabled}
                  value={unsummarizedThreshold}
                  onChange={(e) => setUnsummarizedThreshold(Number(e.target.value))}
                  className="h-8 text-xs font-mono max-w-xs"
                />
              </Field>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
