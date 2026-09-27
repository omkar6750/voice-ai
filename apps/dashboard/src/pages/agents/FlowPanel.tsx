import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { ReadOnlyValue, StatusBadge } from "@/components/record-page";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { PromptEditor } from "./PromptEditor";
import type { AgentConfig, ContactVariablesResponse, FlowNode } from "./types";

export function FlowPanel({
  config,
  change,
  registeredTools,
  variablesCatalog,
  disabled,
}: {
  config: AgentConfig;
  change: (next: AgentConfig) => void;
  registeredTools: string[];
  variablesCatalog?: ContactVariablesResponse | null;
  disabled: boolean;
}) {
  const temporalKeys = (variablesCatalog?.temporal ?? []).map((t) => t.key);
  const contactVariables = config.contact_variables ?? [];
  const verbatimOpening = Boolean(config.greeting?.trim());
  const availableVariables = [
    ...temporalKeys,
    ...contactVariables,
    ...contactVariables.map((v) => `contact.${v}`),
  ];
  const [selectedId, setSelectedId] = useState(config.flow.initial_node);
  const [newId, setNewId] = useState("");
  const node =
    config.flow.nodes.find((item) => item.id === selectedId) ??
    config.flow.nodes[0];
  if (!node) return null;
  const allNodeIds = config.flow.nodes.map((item) => item.id);
  const boundTools = Object.keys(config.tool_bindings);
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
    updateNode({
      ...node,
      [key]: current.includes(value)
        ? current.filter((item) => item !== value)
        : [...current, value],
    });
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[12rem_minmax(0,1fr)]">
      <aside className="flex flex-col gap-2">
        <h2 className="text-sm font-semibold">Nodes</h2>
        {config.flow.nodes.map((item) => (
          <Button
            key={item.id}
            type="button"
            variant={item.id === node.id ? "secondary" : "ghost"}
            className="justify-start"
            onClick={() => setSelectedId(item.id)}
          >
            {item.id}
          </Button>
        ))}
        {!disabled && (
          <div className="flex gap-2">
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
      <section className="flex min-w-0 max-w-3xl flex-col gap-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-semibold">{node.id}</h2>
            {node.terminal && <StatusBadge value="terminal" />}
            {config.flow.initial_node === node.id && (
              <StatusBadge value="initial" />
            )}
          </div>
          {!disabled && config.flow.nodes.length > 1 && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={removeNode}
            >
              <Trash2 data-icon="inline-start" /> Delete node
            </Button>
          )}
        </div>
        <FieldGroup>
          <Field>
            <FieldLabel htmlFor="initial-node">Initial node</FieldLabel>
            <NativeSelect
              id="initial-node"
              value={config.flow.initial_node}
              onChange={(event) =>
                change({
                  ...config,
                  flow: { ...config.flow, initial_node: event.target.value },
                })
              }
              disabled={disabled}
            >
              {allNodeIds.map((id) => (
                <option key={id} value={id}>
                  {id}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <PromptEditor
            id={`node-prompt-${node.id}`}
            label="Node instructions"
            value={node.prompt}
            onChange={(prompt) => updateNode({ ...node, prompt })}
            availableTools={node.tool_bindings}
            registeredTools={registeredTools}
            availableVariables={availableVariables}
            disabled={disabled}
          />
          <Field>
            <FieldLabel htmlFor="context-strategy">Context strategy</FieldLabel>
            <NativeSelect
              id="context-strategy"
              value={node.context_strategy ?? "append"}
              onChange={(event) =>
                updateNode({
                  ...node,
                  context_strategy: event.target.value as "append" | "reset",
                })
              }
              disabled={disabled}
            >
              <option value="append">Append</option>
              <option value="reset">Reset</option>
            </NativeSelect>
            <FieldDescription>
              Append keeps the conversation context; Reset replaces task messages when entering this node.
            </FieldDescription>
          </Field>
          <Field>
            <FieldLabel htmlFor="role-override">Override agent role/system instruction</FieldLabel>
            <NativeSelect
              id="role-override"
              value={node.role_prompt ? "true" : "false"}
              onChange={(event) =>
                updateNode({
                  ...node,
                  role_prompt: event.target.value === "true" ? node.role_prompt || "" : null,
                })
              }
              disabled={disabled}
            >
              <option value="false">No — keep the active role instruction</option>
              <option value="true">Yes — set a node role instruction</option>
            </NativeSelect>
          </Field>
          {node.role_prompt !== null && node.role_prompt !== undefined && (
            <PromptEditor
              id={`node-role-prompt-${node.id}`}
              label="Node role/system instruction"
              value={node.role_prompt}
              onChange={(role_prompt) => updateNode({ ...node, role_prompt })}
              availableTools={node.tool_bindings}
              registeredTools={registeredTools}
              availableVariables={availableVariables}
              disabled={disabled}
            />
          )}          <Field>
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
              value={String(verbatimOpening && node.id === config.flow.initial_node ? false : node.respond_immediately)}
              onChange={(event) =>
                updateNode({
                  ...node,
                  respond_immediately: event.target.value === "true",
                })
              }
              disabled={disabled || (verbatimOpening && node.id === config.flow.initial_node)}
            >
              <option value="true">Yes</option>
              <option value="false">No</option>
            </NativeSelect>
            {verbatimOpening && node.id === config.flow.initial_node && (
              <FieldDescription>
                A verbatim opening is enabled, so this node must wait for the caller before running the LLM.
              </FieldDescription>
            )}
          </Field>
        </FieldGroup>
        {!node.terminal && (
          <div>
            <h3 className="mb-2 text-sm font-semibold">Allowed transitions</h3>
            <div className="flex flex-wrap gap-2">
              {allNodeIds
                .filter((id) => id !== node.id)
                .map((id) => (
                  <Button
                    key={id}
                    type="button"
                    size="sm"
                    variant={
                      node.transitions.includes(id) ? "secondary" : "outline"
                    }
                    aria-pressed={node.transitions.includes(id)}
                    disabled={disabled}
                    onClick={() => toggleIn("transitions", id)}
                  >
                    {id}
                  </Button>
                ))}
            </div>
          </div>
        )}
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
                  : "outline"
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
                  : "outline"
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
        <div>
          <h3 className="mb-2 text-sm font-semibold">
            Tools available in this node
          </h3>
          <div className="flex flex-wrap gap-2">
            {boundTools.length ? (
              boundTools.map((name) => (
                <Button
                  key={name}
                  type="button"
                  size="sm"
                  variant={
                    node.tool_bindings.includes(name) ? "secondary" : "outline"
                  }
                  aria-pressed={node.tool_bindings.includes(name)}
                  disabled={disabled}
                  onClick={() => toggleIn("tool_bindings", name)}
                >
                  {name}
                </Button>
              ))
            ) : (
              <p className="text-sm text-muted-foreground">
                Bind a published tool under Tools first.
              </p>
            )}
          </div>
          {node.tool_bindings.some((name) => !boundTools.includes(name)) && (
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
      </section>
    </div>
  );
}
