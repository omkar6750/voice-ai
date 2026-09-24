import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AudioLines, Bot, ChevronRight, Plus, RefreshCw, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { useApi } from "@/app/api";
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
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from "@/components/ui/empty";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { Field, FieldLabel } from "@/components/ui/field";
import { NativeSelect } from "@/components/ui/native-select";
import { Spinner } from "@/components/ui/spinner";

interface AgentItem {
  id: string;
  name: string;
  active_version_id: string | null;
}

export function AgentsPage() {
  const api = useApi();
  const navigate = useNavigate();
  const [agents, setAgents] = useState<AgentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Create agent sheet state
  const [openAddSheet, setOpenAddSheet] = useState(false);
  const [creating, setCreating] = useState(false);
  const [agentName, setAgentName] = useState("");
  const [systemPrompt, setSystemPrompt] = useState(
    "You are a professional voice assistant. Speak naturally and keep responses concise.",
  );
  const [greetingPrompt, setGreetingPrompt] = useState(
    "Hello! Thanks for reaching out. How can I assist you today?",
  );
  const [llmModel, setLlmModel] = useState("llama-3.3-70b-versatile");
  const [ttsVoice, setTtsVoice] = useState("sonic-english");

  async function load() {
    setLoading(true);
    setError("");
    try {
      const data = await api<{ agents: AgentItem[] }>("/agents");
      setAgents(data.agents);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to load agents";
      setError(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function handleCreateAgent(e: FormEvent) {
    e.preventDefault();
    if (!agentName.trim()) {
      toast.error("Please enter an agent name");
      return;
    }

    setCreating(true);
    try {
      const config = {
        system_prompt: systemPrompt.trim(),
        llm: {
          provider: "groq",
          model: llmModel,
          temperature: 0.7,
        },
        stt: {
          provider: "deepgram",
          model: "nova-3",
          language: "en",
        },
        tts: {
          provider: "cartesia",
          voice: ttsVoice,
        },
        vad: {
          provider: "silero",
          confidence: 0.5,
        },
        flow: {
          initial_node: "greeting",
          nodes: [
            {
              id: "greeting",
              prompt: greetingPrompt.trim(),
              transitions: ["closing"],
              tool_bindings: [],
              entry_actions: [],
              exit_actions: [],
              respond_immediately: true,
              terminal: false,
            },
            {
              id: "closing",
              prompt:
                "Thank the user for their time and conclude the call gracefully.",
              transitions: [],
              tool_bindings: [],
              entry_actions: [],
              exit_actions: [],
              respond_immediately: true,
              terminal: true,
            },
          ],
          prompt_composition: "node_only",
        },
      };

      const res = await api<{ agent_id: string; version_id: string }>("/agents", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: agentName.trim(),
          config,
        }),
      });

      toast.success(`Agent '${agentName}' created with initial draft v1`);
      setOpenAddSheet(false);
      setAgentName("");
      navigate(`/agents/${res.agent_id}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to create agent");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="flex flex-col gap-5 p-6 max-w-6xl mx-auto">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Agents</h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Autonomous conversational voice agents, prompt flows, and versioned pipelines.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => void load()}>
            <RefreshCw className="size-3.5 mr-1.5" /> Refresh
          </Button>
          <Sheet open={openAddSheet} onOpenChange={setOpenAddSheet}>
            <SheetTrigger asChild>
              <Button size="sm" className="gap-1.5 bg-primary text-primary-foreground">
                <Plus className="size-3.5" /> Create Agent
              </Button>
            </SheetTrigger>
            <SheetContent side="right" className="flex flex-col p-6 w-full sm:max-w-lg">
              <SheetHeader className="p-0 mb-4">
                <SheetTitle className="flex items-center gap-2 text-lg">
                  <Bot className="size-5 text-primary" />
                  Create Voice Agent
                </SheetTitle>
                <SheetDescription>
                  Initialize a new conversational voice agent with its initial prompt graph flow.
                </SheetDescription>
              </SheetHeader>

              <form onSubmit={handleCreateAgent} className="flex flex-col gap-4 flex-1 justify-between">
                <div className="flex flex-col gap-3.5 overflow-y-auto pr-1">
                  <Field>
                    <FieldLabel htmlFor="agent-name">Agent Name</FieldLabel>
                    <Input
                      id="agent-name"
                      placeholder="Outbound Sales Qualifier"
                      required
                      value={agentName}
                      onChange={(e) => setAgentName(e.target.value)}
                    />
                  </Field>

                  <Field>
                    <FieldLabel htmlFor="agent-system">System Persona / Instructions</FieldLabel>
                    <Textarea
                      id="agent-system"
                      rows={3}
                      placeholder="You are a helpful voice assistant..."
                      value={systemPrompt}
                      onChange={(e) => setSystemPrompt(e.target.value)}
                    />
                  </Field>

                  <Field>
                    <FieldLabel htmlFor="agent-greeting">Initial Greeting Prompt</FieldLabel>
                    <Textarea
                      id="agent-greeting"
                      rows={2}
                      placeholder="Hello! How can I help you today?"
                      value={greetingPrompt}
                      onChange={(e) => setGreetingPrompt(e.target.value)}
                    />
                  </Field>

                  <div className="grid grid-cols-2 gap-3">
                    <Field>
                      <FieldLabel htmlFor="agent-llm">LLM Model</FieldLabel>
                      <NativeSelect
                        id="agent-llm"
                        value={llmModel}
                        onChange={(e) => setLlmModel(e.target.value)}
                      >
                        <option value="llama-3.3-70b-versatile">Groq Llama 3.3 70B</option>
                        <option value="llama-3.1-8b-instant">Groq Llama 3.1 8B</option>
                        <option value="gemini-2.5-flash">Gemini 2.5 Flash</option>
                      </NativeSelect>
                    </Field>

                    <Field>
                      <FieldLabel htmlFor="agent-tts">TTS Voice</FieldLabel>
                      <NativeSelect
                        id="agent-tts"
                        value={ttsVoice}
                        onChange={(e) => setTtsVoice(e.target.value)}
                      >
                        <option value="sonic-english">Cartesia Sonic (English)</option>
                        <option value="sonic-multilingual">Cartesia Sonic (Multilingual)</option>
                      </NativeSelect>
                    </Field>
                  </div>
                </div>

                <div className="flex items-center justify-end gap-3 pt-4 border-t">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => setOpenAddSheet(false)}
                    disabled={creating}
                  >
                    Cancel
                  </Button>
                  <Button type="submit" disabled={creating || !agentName.trim()}>
                    {creating ? <Spinner className="size-4 mr-1.5" /> : null}
                    Create & Configure Flow
                  </Button>
                </div>
              </form>
            </SheetContent>
          </Sheet>
        </div>
      </div>

      {loading ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((n) => (
            <Card key={n} className="p-4">
              <Skeleton className="h-5 w-32 mb-2" />
              <Skeleton className="h-4 w-48 mb-4" />
              <Skeleton className="h-8 w-20" />
            </Card>
          ))}
        </div>
      ) : error ? (
        <Empty>
          <EmptyHeader>
            <EmptyTitle>Could not load agents</EmptyTitle>
            <EmptyDescription>{error}</EmptyDescription>
          </EmptyHeader>
          <Button variant="outline" size="sm" onClick={() => void load()}>
            Retry
          </Button>
        </Empty>
      ) : agents.length === 0 ? (
        <Empty>
          <EmptyHeader>
            <EmptyTitle>No agents configured</EmptyTitle>
            <EmptyDescription>
              Create an agent to start placing and handling autonomous voice calls.
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {agents.map((agent) => (
            <Card
              key={agent.id}
              className="group flex flex-col justify-between hover:border-border transition-colors shadow-none"
            >
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex size-8 items-center justify-center rounded-md bg-primary/10 text-primary">
                    <AudioLines className="size-4" />
                  </div>
                  {agent.active_version_id ? (
                    <Badge variant="outline" className="bg-emerald-50 text-emerald-700 text-[11px] font-normal border-emerald-200">
                      Active Version
                    </Badge>
                  ) : (
                    <Badge variant="outline" className="text-muted-foreground text-[11px] font-normal">
                      Draft Only
                    </Badge>
                  )}
                </div>
                <CardTitle className="text-sm font-semibold mt-3 group-hover:text-primary transition-colors">
                  {agent.name}
                </CardTitle>
                <CardDescription className="text-xs line-clamp-1 font-mono">
                  ID: {agent.id.slice(0, 12)}…
                </CardDescription>
              </CardHeader>
              <CardContent className="pt-0">
                <Button asChild variant="outline" size="sm" className="w-full justify-between text-xs">
                  <Link to={`/agents/${agent.id}`}>
                    Manage versions
                    <ChevronRight className="size-3.5 text-muted-foreground" />
                  </Link>
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
