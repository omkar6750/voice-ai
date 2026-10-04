import { useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  Plus,
  Trash2,
  Settings2,
  GitBranch,
  Wrench,
  Sparkles,
  Zap,
  Database,
  FileText,
  MessagesSquare,
  Eye,
  Check,
} from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { LeadClassifierRouting } from "./LeadClassifierRouting";
import { NodeList, ConfigGroup } from "./FlowWorkspace";
import { toast } from "sonner";
import { ReadOnlyValue, StatusBadge } from "@/components/record-page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { PromptEditor } from "./PromptEditor";
import type {
  AgentConfig,
  ContactVariablesResponse,
  FlowNode,
  ProviderCatalog,
} from "./types";

export function FlowPanel({
  config,
  change,
  registeredTools,
  variablesCatalog,
  classifierContract,
  disabled,
}: {
  config: AgentConfig;
  change: (next: AgentConfig) => void;
  registeredTools: string[];
  variablesCatalog?: ContactVariablesResponse | null;
  classifierContract?: ProviderCatalog["classifier_contract"];
  disabled: boolean;
}) {
  const temporalKeys = (variablesCatalog?.temporal ?? []).map((t) => t.key);
  const contactVariables = config.contact_variables ?? [];
  const availableVariables = [
    ...temporalKeys,
    ...contactVariables,
    ...contactVariables.map((v) => `contact.${v}`),
    ...(config.fact_slots ?? [])
      .filter((slot) => slot.key)
      .map((slot) => slot.key),
  ];
  const [selectedId, setSelectedId] = useState(config.flow.initial_node);
  const [newId, setNewId] = useState("");
  const node =
    config.flow.nodes.find((item) => item.id === selectedId) ??
    config.flow.nodes[0];
  if (!node) return null;
  const allNodeIds = config.flow.nodes.map((item) => item.id);
  const boundTools = Object.keys(config.tool_bindings);
  const globalFunctionNames = (config.flow.global_functions ?? []).map(
    (item) => item.name,
  );
  type FlowAction = {
    type: string;
    text?: string;
    append_text_to_context?: boolean;
    handler?: string;
  };
  function updateNode(next: FlowNode) {
    change({
      ...config,
      flow: {
        ...config.flow,
        nodes: config.flow.nodes.map((item) =>
          item.id === node.id ? next : item,
        ),
      },
    });
  }
  function addNode() {
    const id = newId.trim();
    if (!/^[a-z][a-z0-9_]*$/.test(id) || allNodeIds.includes(id)) {
      toast.error(
        "Use a unique lowercase node ID with letters, numbers or underscores",
      );
      return;
    }
    change({
      ...config,
      flow: {
        ...config.flow,
        nodes: [
          ...config.flow.nodes,
          {
            id,
            role_message: "",
            task_messages: [],
            functions: [],
            pre_actions: [],
            post_actions: [],
            prompt: "",
            role_prompt: null,
            context_strategy: "append",
            transitions: [],
            tool_bindings: [],
            entry_actions: [],
            exit_actions: [],
            respond_immediately: true,
            terminal: true,
          },
        ],
      },
    });
    setSelectedId(id);
    setNewId("");
  }
  function removeNode() {
    if (config.flow.nodes.length === 1) return;
    const remaining = config.flow.nodes
      .filter((item) => item.id !== node.id)
      .map((item) => ({
        ...item,
        transitions: item.transitions.filter((id) => id !== node.id),
      }));
    const initial_node =
      config.flow.initial_node === node.id
        ? remaining[0].id
        : config.flow.initial_node;
    change({
      ...config,
      flow: { ...config.flow, initial_node, nodes: remaining },
    });
    setSelectedId(initial_node);
  }
  function toggleIn(key: "transitions" | "tool_bindings", value: string) {
    const current = node[key];
    if (key === "tool_bindings" && globalFunctionNames.includes(value)) return;
    if (key === "tool_bindings") {
      const routed = (node.functions ?? []).some(
        (fn) => fn.name === value && !fn.transition_only,
      );
      const enabled = current.includes(value) || routed;
      updateNode({
        ...node,
        tool_bindings: enabled
          ? current.filter((item) => item !== value)
          : [...current, value],
        functions: enabled
          ? (node.functions ?? []).filter(
              (fn) => fn.name !== value || fn.transition_only,
            )
          : node.functions,
      });
      return;
    }
    updateNode({
      ...node,
      [key]: current.includes(value)
        ? current.filter((item) => item !== value)
        : [...current, value],
    });
  }
  function toggleGlobalFunction(name: string) {
    const current = config.flow.global_functions ?? [];
    const enabling = !current.some((item) => item.name === name);
    change({
      ...config,
      flow: {
        ...config.flow,
        global_functions: !enabling
          ? current.filter((item) => item.name !== name)
          : [
              ...current,
              {
                name,
                transition_only: false,
                description: null,
                transition_to: null,
              },
            ],
        nodes: enabling
          ? config.flow.nodes.map((item) => ({
              ...item,
              tool_bindings: item.tool_bindings.filter((tool) => tool !== name),
            }))
          : config.flow.nodes,
      },
    });
  }
  function updateFunction(
    index: number,
    patch: Partial<FlowNode["functions"][number]>,
  ) {
    const functions = [...(node.functions ?? [])];
    functions[index] = { ...functions[index], ...patch };
    updateNode({ ...node, functions });
  }
  function addFunction(name: string) {
    if ((node.functions ?? []).some((item) => item.name === name)) return;
    updateNode({
      ...node,
      tool_bindings: node.tool_bindings.filter((item) => item !== name),
      functions: [
        ...(node.functions ?? []),
        {
          name,
          transition_only: false,
          description: null,
          transition_to: null,
        },
      ],
    });
  }
  function updateAction(
    phase: "pre_actions" | "post_actions",
    index: number,
    updated: FlowAction,
  ) {
    const actions = [...((node[phase] ?? []) as FlowAction[])];
    actions[index] = updated;
    updateNode({ ...node, [phase]: actions });
  }
  function addAction(
    phase: "pre_actions" | "post_actions",
    action: FlowAction,
  ) {
    const actions = [...((node[phase] ?? []) as FlowAction[]), action];
    updateNode({ ...node, [phase]: actions });
  }
  function renderActions(phase: "pre_actions" | "post_actions") {
    const actions = (node[phase] ?? []) as FlowAction[];
    return (
      <div className="grid gap-3 rounded-md border p-3">
        <div>
          <h3 className="text-sm font-semibold">{phase}</h3>
          <p className="text-xs text-muted-foreground">
            Pipecat runs these in order{" "}
            {phase === "pre_actions" ? "before" : "after"} the node response.
          </p>
        </div>
        {actions.map((action, index) => (
          <div
            key={`${action.type}-${index}`}
            className="grid gap-2 rounded-md bg-muted/40 p-3"
          >
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">{action.type}</span>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                disabled={disabled}
                aria-label={`Remove ${phase} action ${index + 1}`}
                onClick={() =>
                  updateNode({
                    ...node,
                    [phase]: actions.filter(
                      (_, actionIndex) => actionIndex !== index,
                    ),
                  })
                }
              >
                <Trash2 className="size-4" />
              </Button>
            </div>
            {action.type === "tts_say" ? (
              <Field>
                <FieldLabel>text</FieldLabel>
                <Textarea
                  value={action.text ?? ""}
                  disabled={disabled}
                  onChange={(event) =>
                    updateAction(phase, index, {
                      ...action,
                      text: event.target.value,
                    })
                  }
                />
              </Field>
            ) : action.type === "function" ? (
              <Field>
                <FieldLabel>handler</FieldLabel>
                <NativeSelect
                  value={action.handler ?? ""}
                  disabled={disabled}
                  onChange={(event) =>
                    updateAction(phase, index, {
                      ...action,
                      handler: event.target.value,
                    })
                  }
                >
                  <option value="">Choose a bound action tool</option>
                  {boundTools.map((name) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
                </NativeSelect>
              </Field>
            ) : null}
          </div>
        ))}
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={disabled}
            onClick={() =>
              addAction(phase, {
                type: "tts_say",
                text: "",
                append_text_to_context: true,
              })
            }
          >
            Add tts_say
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={disabled || !boundTools.length}
            onClick={() => addAction(phase, { type: "function", handler: "" })}
          >
            Add function
          </Button>
        </div>
      </div>
    );
  }
  function updateFactSlot(
    index: number,
    next: Partial<AgentConfig["fact_slots"][number]>,
  ) {
    const slots = [...(config.fact_slots ?? [])];
    slots[index] = { ...slots[index], ...next };
    change({ ...config, fact_slots: slots });
  }
  function addFactSlot() {
    const existing = config.fact_slots ?? [];
    let key = "caller_fact";
    let suffix = 2;
    while (existing.some((slot) => slot.key === key))
      key = `caller_fact_${suffix++}`;
    change({
      ...config,
      fact_slots: [
        ...existing,
        {
          key,
          description: "A useful fact shared by the caller",
          value_type: "string",
          enum: null,
          minimum: null,
          maximum: null,
          nodes: [],
        },
      ],
    });
  }

  const selectedIndex = config.flow.nodes.findIndex(
    (item) => item.id === node.id,
  );
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          Build the conversation one node at a time.
        </p>
        <div className="flex items-center gap-3">
          <span className="text-xs text-muted-foreground">
            {allNodeIds.length} nodes
          </span>
          <label
            htmlFor="initial-node"
            className="text-xs text-muted-foreground"
          >
            Start at
          </label>
          <NativeSelect
            id="initial-node"
            className="w-48"
            value={config.flow.initial_node}
            disabled={disabled}
            onChange={(event) =>
              change({
                ...config,
                flow: { ...config.flow, initial_node: event.target.value },
              })
            }
          >
            {allNodeIds.map((id) => (
              <option key={id} value={id}>
                {id}
              </option>
            ))}
          </NativeSelect>
        </div>
      </div>
      <div className="grid items-start gap-4 lg:grid-cols-[13rem_minmax(0,1fr)] xl:grid-cols-[14rem_minmax(0,1.25fr)_minmax(20rem,0.9fr)]">
        <aside
          aria-label="Flow nodes"
          className="flex min-w-0 flex-col gap-4 rounded-xl bg-editor-surface p-3 lg:sticky lg:top-4"
        >
          <div>
            <h2 className="flex items-center gap-2 text-sm font-semibold">
              Nodes <Badge variant="secondary">{allNodeIds.length}</Badge>
            </h2>
            <p className="mt-1 text-xs text-muted-foreground">
              Drag the handle to reorder. Select a node to edit.
            </p>
          </div>
          <NodeList
            nodes={config.flow.nodes}
            selectedId={node.id}
            initialId={config.flow.initial_node}
            disabled={disabled}
            select={setSelectedId}
            reorder={(nodes) =>
              change({ ...config, flow: { ...config.flow, nodes } })
            }
          />
          <p id="node-reorder-help" className="text-xs text-muted-foreground">
            Order changes this list only. Transitions control routing. Keyboard:
            Space to pick up, arrows to move, Space to drop.
          </p>
          {!disabled && (
            <div className="flex gap-2 border-t pt-3">
              <Input
                aria-label="New node ID"
                placeholder="new_node"
                value={newId}
                onChange={(event) => setNewId(event.target.value)}
              />
              <Button
                type="button"
                size="icon"
                variant="outline"
                onClick={addNode}
                aria-label="Add node"
              >
                <Plus />
              </Button>
            </div>
          )}
        </aside>
        <section
          aria-label="Node prompt workspace"
          className="flex min-w-0 flex-col rounded-xl bg-editor-surface"
        >
          <header className="flex flex-col gap-3 p-4">
            <div className="flex items-center justify-between gap-2">
              <div className="flex min-w-0 items-center gap-2">
                <h2 className="truncate text-lg font-semibold" title={node.id}>
                  {node.id}
                </h2>
              </div>
              <div className="flex shrink-0 items-center gap-1">
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label="Previous node"
                  disabled={selectedIndex === 0}
                  onClick={() => setSelectedId(allNodeIds[selectedIndex - 1])}
                >
                  <ChevronLeft />
                </Button>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label="Next node"
                  disabled={selectedIndex === allNodeIds.length - 1}
                  onClick={() => setSelectedId(allNodeIds[selectedIndex + 1])}
                >
                  <ChevronRight />
                </Button>
                {!disabled && (
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`Delete node ${node.id}`}
                    disabled={allNodeIds.length < 2}
                    onClick={removeNode}
                  >
                    <Trash2 />
                  </Button>
                )}
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              {node.id === config.flow.initial_node && (
                <Badge variant="secondary">Initial</Badge>
              )}
              <Badge variant="secondary">
                {node.transitions.length} routes
              </Badge>
              <Badge variant="secondary">
                {node.respond_immediately
                  ? "Responds on entry"
                  : "Waits for input"}
              </Badge>
              <Badge variant="secondary">
                {node.terminal ? "Terminal" : "Not terminal"}
              </Badge>
            </div>
          </header>
          <Tabs defaultValue="prompt" className="min-w-0 gap-0">
            <TabsList variant="line" className="mx-3 my-2">
              <TabsTrigger value="prompt">
                <FileText className="size-4" /> Prompt
              </TabsTrigger>
              <TabsTrigger value="tasks">
                <MessagesSquare className="size-4" /> Task messages
              </TabsTrigger>
              <TabsTrigger value="preview">
                <Eye className="size-4" /> Preview
              </TabsTrigger>
            </TabsList>
            <TabsContent value="prompt" className="min-w-0 p-4">
              <FieldGroup>
                <PromptEditor
                  id={`node-prompt-${node.id}`}
                  label="System instruction (role_message)"
                  value={node.role_message ?? node.role_prompt ?? node.prompt}
                  onChange={(role_message) =>
                    updateNode({
                      ...node,
                      role_message,
                      role_prompt: null,
                      prompt: "",
                    })
                  }
                  availableTools={[
                    ...new Set([
                      ...node.tool_bindings,
                      ...globalFunctionNames,
                      ...(node.transitions ?? []).map(
                        (target) => `go_to_${target}`,
                      ),
                      ...(config.fact_slots ?? [])
                        .filter(
                          (slot) =>
                            slot.key &&
                            (!slot.nodes?.length ||
                              slot.nodes.includes(node.id)),
                        )
                        .map((slot) => `record_${slot.key}`),
                      ...(node.functions ?? [])
                        .filter((fn) => !fn.transition_only)
                        .map((fn) => fn.name),
                    ]),
                  ]}
                  registeredTools={registeredTools}
                  availableVariables={availableVariables}
                  disabled={disabled}
                />
              </FieldGroup>
            </TabsContent>
            <TabsContent value="tasks" className="min-w-0 p-4">
              <FieldGroup>
                <Field>
                  <FieldLabel>Task messages (task_messages)</FieldLabel>
                  <FieldDescription>
                    These are added to conversation context with the selected
                    role. Put persona and node instructions in role_message
                    above so provider adapters keep them in the system
                    instruction.
                  </FieldDescription>
                  <div className="flex flex-col gap-3">
                    {(node.task_messages ?? []).map((message, index) => (
                      <div
                        key={`${node.id}-task-${index}`}
                        className="flex flex-col gap-2 rounded-md border p-3"
                      >
                        <div className="flex items-center gap-2">
                          <NativeSelect
                            aria-label={`Task message ${index + 1} role`}
                            value={message.role}
                            onChange={(event) => {
                              const task_messages = [...node.task_messages];
                              task_messages[index] = {
                                ...message,
                                role: event.target
                                  .value as FlowNode["task_messages"][number]["role"],
                              };
                              updateNode({ ...node, task_messages });
                            }}
                            disabled={disabled}
                          >
                            <option value="user">user</option>
                            <option value="assistant">assistant</option>
                            <option value="system">system</option>
                            <option value="developer">developer</option>
                          </NativeSelect>
                          <Button
                            type="button"
                            size="icon"
                            variant="ghost"
                            aria-label={`Remove task message ${index + 1}`}
                            onClick={() =>
                              updateNode({
                                ...node,
                                task_messages: node.task_messages.filter(
                                  (_, i) => i !== index,
                                ),
                              })
                            }
                            disabled={disabled}
                          >
                            <Trash2 />
                          </Button>
                        </div>
                        <Textarea
                          aria-label={`Task message ${index + 1} content`}
                          value={message.content}
                          onChange={(event) => {
                            const task_messages = [...node.task_messages];
                            task_messages[index] = {
                              ...message,
                              content: event.target.value,
                            };
                            updateNode({ ...node, task_messages });
                          }}
                          disabled={disabled}
                          rows={3}
                        />
                      </div>
                    ))}
                    <Button
                      type="button"
                      variant="outline"
                      className="self-start"
                      onClick={() =>
                        updateNode({
                          ...node,
                          task_messages: [
                            ...node.task_messages,
                            { role: "user", content: "" },
                          ],
                        })
                      }
                      disabled={disabled}
                    >
                      <Plus /> Add task message
                    </Button>
                  </div>
                </Field>
              </FieldGroup>
            </TabsContent>
            <TabsContent value="preview" className="min-w-0 p-4">
              <p className="mb-3 text-xs text-muted-foreground">
                Saved instructions for this node, before runtime variable
                substitution and conversation history.
              </p>
              <pre className="max-h-[36rem] overflow-auto whitespace-pre-wrap break-words font-mono text-xs leading-6">
                {JSON.stringify(
                  {
                    global_system_instruction: config.system_prompt,
                    role_message:
                      node.role_message ?? node.role_prompt ?? node.prompt,
                    task_messages: node.task_messages,
                    context_strategy: node.context_strategy,
                  },
                  null,
                  2,
                )}
              </pre>
            </TabsContent>
          </Tabs>
        </section>
        <aside
          aria-label="Node settings"
          className="flex min-w-0 flex-col gap-3 rounded-xl bg-editor-surface p-3 lg:col-start-2 xl:col-start-auto"
        >
          <div className="px-1">
            <h2 className="text-sm font-semibold">Node settings</h2>
            <p className="mt-1 text-xs text-muted-foreground">
              Behavior, routing, tools and conversation facts.
            </p>
          </div>
          <ConfigGroup title="General" icon={Settings2} defaultOpen>
            <ReadOnlyValue label="Node ID" value={node.id} />
            <FieldGroup>
              <Field>
                <FieldLabel htmlFor="context-strategy">
                  Context strategy
                </FieldLabel>
                <NativeSelect
                  id="context-strategy"
                  value={node.context_strategy ?? "append"}
                  onChange={(event) =>
                    updateNode({
                      ...node,
                      context_strategy: event.target.value as
                        "append" | "reset",
                    })
                  }
                  disabled={disabled}
                >
                  <option value="append">Append</option>
                  <option value="reset">Reset</option>
                </NativeSelect>
                <FieldDescription>
                  Append keeps earlier dialogue and node messages. Reset
                  replaces the entire LLM message list, including prior caller
                  and agent turns; saved transcripts remain in run evidence, not
                  in the next LLM request.
                </FieldDescription>
              </Field>
              <Field>
                <FieldLabel htmlFor="terminal-node">Terminal node</FieldLabel>
                <NativeSelect
                  id="terminal-node"
                  value={String(node.terminal)}
                  onChange={(event) =>
                    updateNode({
                      ...node,
                      terminal: event.target.value === "true",
                      transitions:
                        event.target.value === "true" ? [] : node.transitions,
                    })
                  }
                  disabled={disabled}
                >
                  <option value="false">No</option>
                  <option value="true">Yes</option>
                </NativeSelect>
              </Field>
              <Field>
                <FieldLabel htmlFor="immediate-response">
                  Respond on entry
                </FieldLabel>
                <NativeSelect
                  id="immediate-response"
                  value={String(node.respond_immediately)}
                  onChange={(event) =>
                    updateNode({
                      ...node,
                      respond_immediately: event.target.value === "true",
                    })
                  }
                  disabled={disabled}
                >
                  <option value="true">Yes</option>
                  <option value="false">No</option>
                </NativeSelect>
              </Field>
            </FieldGroup>
          </ConfigGroup>
          <ConfigGroup
            title="Transitions"
            icon={GitBranch}
            summary={`${node.transitions.length}`}
            defaultOpen
          >
            {node.terminal && (
              <p className="text-xs text-muted-foreground">
                Terminal nodes end the call and have no transitions.
              </p>
            )}
            {!node.terminal && (
              <div>
                <h3 className="mb-2 text-sm font-semibold">
                  Allowed transitions
                </h3>
                <div className="flex flex-wrap gap-2">
                  {allNodeIds
                    .filter((id) => id !== node.id)
                    .map((id) => (
                      <Button
                        key={id}
                        type="button"
                        size="sm"
                        variant={
                          node.transitions.includes(id) ? "secondary" : "choice"
                        }
                        aria-pressed={node.transitions.includes(id)}
                        disabled={disabled}
                        onClick={() => toggleIn("transitions", id)}
                      >
                        {node.transitions.includes(id) && (
                          <Check data-icon="inline-start" />
                        )}
                        {id}
                      </Button>
                    ))}
                </div>
              </div>
            )}
          </ConfigGroup>
          <ConfigGroup title="Classifier" icon={Sparkles}>
            <div>
              <h3 className="mb-2 text-sm font-semibold">
                Classifier triggers for this node
              </h3>
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant={
                    (config.classifier.node_entries ?? []).includes(node.id)
                      ? "default"
                      : "choice"
                  }
                  aria-pressed={(config.classifier.node_entries ?? []).includes(
                    node.id,
                  )}
                  disabled={disabled}
                  onClick={() => {
                    const current = config.classifier.node_entries ?? [];
                    const next = current.includes(node.id)
                      ? current.filter((id) => id !== node.id)
                      : [...current, node.id];
                    change({
                      ...config,
                      classifier: { ...config.classifier, node_entries: next },
                    });
                  }}
                >
                  {(config.classifier.node_entries ?? []).includes(node.id)
                    ? "✓ Triggers on entry"
                    : "Trigger on entry"}
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant={
                    (config.classifier.node_exits ?? []).includes(node.id)
                      ? "default"
                      : "choice"
                  }
                  aria-pressed={(config.classifier.node_exits ?? []).includes(
                    node.id,
                  )}
                  disabled={disabled}
                  onClick={() => {
                    const current = config.classifier.node_exits ?? [];
                    const next = current.includes(node.id)
                      ? current.filter((id) => id !== node.id)
                      : [...current, node.id];
                    change({
                      ...config,
                      classifier: { ...config.classifier, node_exits: next },
                    });
                  }}
                >
                  {(config.classifier.node_exits ?? []).includes(node.id)
                    ? "✓ Triggers on exit"
                    : "Trigger on exit"}
                </Button>
              </div>
            </div>
          </ConfigGroup>
          <ConfigGroup
            title="Tools"
            icon={Wrench}
            summary={`${node.tool_bindings.length + (node.functions ?? []).filter((fn) => !fn.transition_only).length}`}
          >
            <section className="flex flex-col gap-2">
              <h3 className="text-sm font-semibold">Tools this step can use</h3>
              <p className="mb-3 mt-1 text-xs text-muted-foreground">
                Choose tools this step may call. Tools marked “Every step” are
                already available here.
              </p>
              {globalFunctionNames.length > 0 && (
                <div className="mb-3 flex flex-wrap gap-2">
                  {globalFunctionNames.map((name) => (
                    <Badge key={name} variant="secondary">
                      {name}
                      <span className="ml-1 font-normal opacity-70">
                        Every step
                      </span>
                    </Badge>
                  ))}
                </div>
              )}
              <div className="mb-4 flex flex-wrap gap-2">
                {boundTools
                  .filter((name) => !globalFunctionNames.includes(name))
                  .map((name) => (
                    <Button
                      key={name}
                      type="button"
                      size="sm"
                      variant={
                        node.tool_bindings.includes(name) ||
                        (node.functions ?? []).some(
                          (fn) => fn.name === name && !fn.transition_only,
                        )
                          ? "secondary"
                          : "choice"
                      }
                      aria-pressed={
                        node.tool_bindings.includes(name) ||
                        (node.functions ?? []).some(
                          (fn) => fn.name === name && !fn.transition_only,
                        )
                      }
                      disabled={disabled}
                      onClick={() => toggleIn("tool_bindings", name)}
                    >
                      {(node.tool_bindings.includes(name) ||
                        (node.functions ?? []).some(
                          (fn) => fn.name === name && !fn.transition_only,
                        )) && <Check data-icon="inline-start" />}
                      {name}
                    </Button>
                  ))}
                {!boundTools.length && (
                  <p className="text-sm text-muted-foreground">
                    No published tools are connected yet. Connect one in the
                    Tools tab.
                  </p>
                )}
              </div>
              <h4 className="mb-1 text-sm font-medium">Where a tool leads</h4>
              <p className="mb-3 text-xs text-muted-foreground">
                After a tool runs, keep this step active, go to one step, or
                route based on its result.
              </p>
              <div className="grid gap-3">
                {(node.functions ?? [])
                  .map((fn, index) => ({ fn, index }))
                  .filter(({ fn }) => !fn.transition_only)
                  .map(({ fn, index }) => {
                    const branch =
                      fn.transition_to && typeof fn.transition_to === "object"
                        ? fn.transition_to
                        : null;
                    return (
                      <div
                        key={`${fn.name}-${index}`}
                        className="grid gap-2 rounded-md border p-3"
                      >
                        <div className="flex items-center justify-between">
                          <strong className="text-sm">{fn.name}</strong>
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            disabled={disabled}
                            onClick={() =>
                              updateNode({
                                ...node,
                                functions: node.functions.filter(
                                  (_, itemIndex) => itemIndex !== index,
                                ),
                              })
                            }
                          >
                            Remove
                          </Button>
                        </div>
                        <Field>
                          <FieldLabel>transition_to</FieldLabel>
                          <NativeSelect
                            aria-label="transition_to"
                            value={
                              typeof fn.transition_to === "string"
                                ? fn.transition_to
                                : branch
                                  ? "__branch__"
                                  : "__none__"
                            }
                            disabled={disabled}
                            onChange={(event) =>
                              updateFunction(index, {
                                transition_to:
                                  event.target.value === "__none__"
                                    ? null
                                    : event.target.value === "__branch__"
                                      ? {
                                          field:
                                            fn.name === "classify_lead"
                                              ? "classification_key"
                                              : "status",
                                          cases: {},
                                          default: null,
                                        }
                                      : event.target.value,
                              })
                            }
                          >
                            <option value="__none__">Stay on this node</option>
                            <option value="__branch__">
                              Branch on tool result
                            </option>
                            {allNodeIds.map((id) => (
                              <option key={id} value={id}>
                                {id}
                              </option>
                            ))}
                          </NativeSelect>
                        </Field>
                        {branch ? (
                          fn.name === "classify_lead" ? (
                            <LeadClassifierRouting
                              branch={branch}
                              contract={classifierContract}
                              nodeIds={allNodeIds}
                              disabled={disabled}
                              onChange={(transition_to) =>
                                updateFunction(index, { transition_to })
                              }
                            />
                          ) : (
                            <>
                              <Field>
                                <FieldLabel>field</FieldLabel>
                                <Input
                                  aria-label="field"
                                  value={branch.field}
                                  disabled={disabled}
                                  onChange={(event) =>
                                    updateFunction(index, {
                                      transition_to: {
                                        ...branch,
                                        field: event.target.value,
                                      },
                                    })
                                  }
                                />
                              </Field>
                              {Object.entries(branch.cases).map(
                                ([caseValue, target]) => (
                                  <div
                                    key={caseValue}
                                    className="grid gap-2 sm:grid-cols-3"
                                  >
                                    <Input
                                      aria-label="branch result value"
                                      value={caseValue}
                                      disabled={disabled}
                                      onChange={(event) => {
                                        const cases = { ...branch.cases };
                                        delete cases[caseValue];
                                        cases[event.target.value] = target;
                                        updateFunction(index, {
                                          transition_to: { ...branch, cases },
                                        });
                                      }}
                                    />
                                    <NativeSelect
                                      aria-label="branch destination"
                                      value={target}
                                      disabled={disabled}
                                      onChange={(event) =>
                                        updateFunction(index, {
                                          transition_to: {
                                            ...branch,
                                            cases: {
                                              ...branch.cases,
                                              [caseValue]: event.target.value,
                                            },
                                          },
                                        })
                                      }
                                    >
                                      {allNodeIds.map((id) => (
                                        <option key={id} value={id}>
                                          {id}
                                        </option>
                                      ))}
                                    </NativeSelect>
                                    <Button
                                      type="button"
                                      variant="ghost"
                                      size="sm"
                                      disabled={disabled}
                                      onClick={() => {
                                        const cases = { ...branch.cases };
                                        delete cases[caseValue];
                                        updateFunction(index, {
                                          transition_to: { ...branch, cases },
                                        });
                                      }}
                                    >
                                      Remove case
                                    </Button>
                                  </div>
                                ),
                              )}
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                disabled={disabled}
                                onClick={() =>
                                  updateFunction(index, {
                                    transition_to: {
                                      ...branch,
                                      cases: {
                                        ...branch.cases,
                                        [`case_${Object.keys(branch.cases).length + 1}`]:
                                          allNodeIds[0],
                                      },
                                    },
                                  })
                                }
                              >
                                Add branch case
                              </Button>
                              <Field>
                                <FieldLabel>default</FieldLabel>
                                <NativeSelect
                                  value={branch.default ?? "__none__"}
                                  disabled={disabled}
                                  onChange={(event) =>
                                    updateFunction(index, {
                                      transition_to: {
                                        ...branch,
                                        default:
                                          event.target.value === "__none__"
                                            ? null
                                            : event.target.value,
                                      },
                                    })
                                  }
                                >
                                  <option value="__none__">
                                    Stay if unmatched
                                  </option>
                                  {allNodeIds.map((id) => (
                                    <option key={id} value={id}>
                                      {id}
                                    </option>
                                  ))}
                                </NativeSelect>
                              </Field>
                            </>
                          )
                        ) : null}
                      </div>
                    );
                  })}
                <Field>
                  <FieldLabel>Add tool routing</FieldLabel>
                  <NativeSelect
                    aria-label="Add tool routing"
                    value=""
                    disabled={disabled}
                    onChange={(event) => {
                      if (event.target.value) addFunction(event.target.value);
                    }}
                  >
                    <option value="">Choose a connected tool…</option>
                    {boundTools
                      .filter(
                        (name) =>
                          !(node.functions ?? []).some(
                            (fn) => fn.name === name,
                          ) && !globalFunctionNames.includes(name),
                      )
                      .map((name) => (
                        <option key={name} value={name}>
                          {name}
                        </option>
                      ))}
                  </NativeSelect>
                </Field>
              </div>
            </section>
            <div>
              <h3 className="mb-2 text-sm font-semibold">Tool connections</h3>
              <p className="text-sm text-muted-foreground">
                To create a tool or connect a published version, open the Tools
                tab. Then choose which steps can use it above.
              </p>
              {node.tool_bindings.some(
                (name) => !boundTools.includes(name),
              ) && (
                <div className="mt-3 flex flex-col gap-1.5 rounded-md border border-destructive/30 bg-destructive/5 p-3">
                  <span className="text-xs font-medium text-destructive">
                    Unbound tool bindings on this node (click to remove):
                  </span>
                  <div className="flex flex-wrap gap-2">
                    {node.tool_bindings
                      .filter((name) => !boundTools.includes(name))
                      .map((name) => (
                        <Button
                          key={name}
                          type="button"
                          size="sm"
                          variant="destructive"
                          disabled={disabled}
                          onClick={() => toggleIn("tool_bindings", name)}
                          title={`Click to remove unbound tool ${name}`}
                        >
                          ✕ {name} (Unbound)
                        </Button>
                      ))}
                  </div>
                </div>
              )}
            </div>
          </ConfigGroup>
          <ConfigGroup
            title="Actions"
            icon={Zap}
            summary={`${(node.pre_actions ?? []).length + (node.post_actions ?? []).length}`}
          >
            <div className="grid gap-3">
              {renderActions("pre_actions")}
              {renderActions("post_actions")}
            </div>
            <div>
              <ReadOnlyValue
                label="Entry actions"
                value={node.entry_actions.join(", ") || "None"}
                reason="Action editing needs runtime-safe handler validation."
              />
              <ReadOnlyValue
                label="Exit actions"
                value={node.exit_actions.join(", ") || "None"}
              />
            </div>
          </ConfigGroup>
          <ConfigGroup
            title="Conversation facts"
            icon={Database}
            summary={`${(config.fact_slots ?? []).length}`}
          >
            <p className="text-xs text-muted-foreground">
              Shared across this agent. Each fact can be limited to selected
              nodes.
            </p>
            <div className="grid gap-3">
              <div>
                <h3 className="text-sm font-semibold">
                  Conversation facts (flow state)
                </h3>
                <p className="text-xs text-muted-foreground">
                  Each slot creates a fixed-key record tool in selected nodes.
                  Values remain in FlowManager.state across context resets.
                </p>
              </div>
              {(config.fact_slots ?? []).map((slot, index) => (
                <div
                  key={index}
                  className="grid gap-3 rounded-md bg-muted/40 p-3"
                >
                  <div className="flex items-end gap-2">
                    <Field className="flex-1">
                      <FieldLabel>state key</FieldLabel>
                      <Input
                        value={slot.key}
                        disabled={disabled}
                        onChange={(event) =>
                          updateFactSlot(index, { key: event.target.value })
                        }
                      />
                    </Field>
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      disabled={disabled}
                      aria-label={`Remove fact slot ${slot.key}`}
                      onClick={() =>
                        change({
                          ...config,
                          fact_slots: (config.fact_slots ?? []).filter(
                            (_, slotIndex) => slotIndex !== index,
                          ),
                        })
                      }
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  </div>
                  <Field>
                    <FieldLabel>Description</FieldLabel>
                    <Input
                      value={slot.description}
                      disabled={disabled}
                      onChange={(event) =>
                        updateFactSlot(index, {
                          description: event.target.value,
                        })
                      }
                    />
                    <FieldDescription>
                      Used to create a narrow record_{slot.key} function
                      description.
                    </FieldDescription>
                  </Field>
                  <Field>
                    <FieldLabel>value_type</FieldLabel>
                    <NativeSelect
                      value={slot.value_type}
                      disabled={disabled}
                      onChange={(event) =>
                        updateFactSlot(index, {
                          value_type: event.target
                            .value as typeof slot.value_type,
                          minimum: null,
                          maximum: null,
                          enum: null,
                        })
                      }
                    >
                      <option value="string">string</option>
                      <option value="integer">integer</option>
                      <option value="number">number</option>
                      <option value="boolean">boolean</option>
                    </NativeSelect>
                  </Field>
                  {slot.value_type === "integer" ||
                  slot.value_type === "number" ? (
                    <div className="grid gap-3 sm:grid-cols-2">
                      <Field>
                        <FieldLabel>minimum</FieldLabel>
                        <Input
                          type="number"
                          value={slot.minimum ?? ""}
                          disabled={disabled}
                          onChange={(event) =>
                            updateFactSlot(index, {
                              minimum:
                                event.target.value === ""
                                  ? null
                                  : Number(event.target.value),
                            })
                          }
                        />
                      </Field>
                      <Field>
                        <FieldLabel>maximum</FieldLabel>
                        <Input
                          type="number"
                          value={slot.maximum ?? ""}
                          disabled={disabled}
                          onChange={(event) =>
                            updateFactSlot(index, {
                              maximum:
                                event.target.value === ""
                                  ? null
                                  : Number(event.target.value),
                            })
                          }
                        />
                      </Field>
                    </div>
                  ) : null}
                  <Field>
                    <FieldLabel>Available in nodes</FieldLabel>
                    <div className="flex flex-wrap gap-2">
                      {allNodeIds.map((nodeId) => {
                        const available =
                          slot.nodes.length === 0 ||
                          slot.nodes.includes(nodeId);
                        return (
                          <Button
                            key={nodeId}
                            type="button"
                            size="sm"
                            variant={available ? "secondary" : "choice"}
                            aria-pressed={available}
                            disabled={disabled}
                            onClick={() => {
                              const selected =
                                slot.nodes.length === 0
                                  ? allNodeIds
                                  : [...slot.nodes];
                              const next = selected.includes(nodeId)
                                ? selected.filter((item) => item !== nodeId)
                                : [...selected, nodeId];
                              updateFactSlot(index, {
                                nodes:
                                  next.length === allNodeIds.length ? [] : next,
                              });
                            }}
                          >
                            {nodeId}
                          </Button>
                        );
                      })}
                    </div>
                    <FieldDescription>
                      Empty means available in every node.
                    </FieldDescription>
                  </Field>
                </div>
              ))}
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="self-start"
                disabled={disabled}
                onClick={addFactSlot}
              >
                <Plus /> Add fact slot
              </Button>
            </div>
          </ConfigGroup>
          <ConfigGroup
            title="Shared tools"
            icon={Wrench}
            summary={`${globalFunctionNames.length}`}
          >
            <div>
              <h3 className="mb-2 text-sm font-semibold">
                Available in every step
              </h3>
              <p className="mb-2 text-xs text-muted-foreground">
                Selected tools are callable from every node. Click a chip to
                enable or disable shared availability. Node-specific tools and
                routing remain configured in the Tools section above.
              </p>
              <div className="flex flex-wrap gap-2">
                {boundTools.map((name) => (
                  <Button
                    key={name}
                    type="button"
                    size="sm"
                    variant={
                      (config.flow.global_functions ?? []).some(
                        (item) => item.name === name,
                      )
                        ? "secondary"
                        : "choice"
                    }
                    aria-pressed={(config.flow.global_functions ?? []).some(
                      (item) => item.name === name,
                    )}
                    disabled={disabled}
                    title={
                      globalFunctionNames.includes(name)
                        ? "Disable shared tool"
                        : "Enable in every node"
                    }
                    onClick={() => toggleGlobalFunction(name)}
                  >
                    {globalFunctionNames.includes(name) && (
                      <Check data-icon="inline-start" />
                    )}
                    {name}
                  </Button>
                ))}
              </div>
              {(config.flow.global_functions ?? [])
                .filter((fn) => fn.name === "classify_lead")
                .map((fn) => {
                  const branch =
                    fn.transition_to && typeof fn.transition_to === "object"
                      ? fn.transition_to
                      : null;
                  const update = (transition_to: typeof fn.transition_to) =>
                    change({
                      ...config,
                      flow: {
                        ...config.flow,
                        global_functions: config.flow.global_functions.map(
                          (item) =>
                            item.name === fn.name
                              ? { ...item, transition_to }
                              : item,
                        ),
                      },
                    });
                  return (
                    <section key={fn.name} className="mt-3 grid gap-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <h4 className="text-sm font-semibold">
                          classify_lead · Shared routing
                        </h4>
                        <Button
                          type="button"
                          size="sm"
                          variant="ghost"
                          disabled={disabled}
                          aria-label="Disable shared tool classify_lead"
                          onClick={() => toggleGlobalFunction(fn.name)}
                        >
                          Disable shared tool
                        </Button>
                      </div>
                      <p className="text-xs text-muted-foreground">
                        This routing applies wherever the shared classifier is
                        called. Use node-specific routing when only discovery
                        should choose the follow-up node.
                      </p>
                      <NativeSelect
                        aria-label="Shared classifier routing mode"
                        disabled={disabled}
                        value={
                          branch
                            ? "__branch__"
                            : typeof fn.transition_to === "string"
                              ? fn.transition_to
                              : "__stay__"
                        }
                        onChange={(event) =>
                          update(
                            event.target.value === "__branch__"
                              ? {
                                  field: "classification_key",
                                  cases: {},
                                  default: null,
                                }
                              : event.target.value === "__stay__"
                                ? null
                                : event.target.value,
                          )
                        }
                      >
                        <option value="__stay__">Stay on this node</option>
                        <option value="__branch__">
                          Branch on tool result
                        </option>
                        {allNodeIds.map((id) => (
                          <option key={id} value={id}>
                            {id}
                          </option>
                        ))}
                      </NativeSelect>
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        disabled={disabled || fn.transition_to == null}
                        onClick={() => update(null)}
                      >
                        Clear shared routing
                      </Button>
                      {branch && (
                        <LeadClassifierRouting
                          branch={branch}
                          contract={classifierContract}
                          nodeIds={allNodeIds}
                          disabled={disabled}
                          onChange={update}
                        />
                      )}
                    </section>
                  );
                })}
            </div>
          </ConfigGroup>
        </aside>
      </div>
    </div>
  );
}
