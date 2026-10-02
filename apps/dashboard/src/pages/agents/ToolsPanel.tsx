import { useState } from "react";
import { toast } from "sonner";
import { LoadState, ReadOnlyValue } from "@/components/record-page";
import { Button } from "@/components/ui/button";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { useResource } from "@/lib/resources";
import { CopyId } from "@/pages/tools/workspace";
import type { AgentConfig, ToolSummary, ToolVersion } from "./types";

function VersionPicker({
  tool,
  onBind,
}: {
  tool: ToolSummary;
  onBind: (version: ToolVersion) => void;
}) {
  const { data, loading, error } = useResource<{ versions: ToolVersion[] }>(
    `/tools/${tool.id}/versions`,
  );
  const published =
    data?.versions.filter((version) => version.status === "published") ?? [];
  return (
    <LoadState
      loading={loading}
      error={error}
      empty={
        !loading && !published.length
          ? "No published versions of this tool."
          : undefined
      }
    >
      <div className="flex flex-wrap gap-2">
        {published.map((version) => (
          <Button
            type="button"
            key={version.id}
            variant="outline"
            size="sm"
            onClick={() => onBind(version)}
          >
            Bind v{version.version} · {version.config.kind}
          </Button>
        ))}
      </div>
    </LoadState>
  );
}

export function ToolsPanel({
  config,
  change,
  disabled,
}: {
  config: AgentConfig;
  change: (next: AgentConfig) => void;
  disabled: boolean;
}) {
  const { data, loading, error } = useResource<{ tools: ToolSummary[] }>(
    "/tools",
  );
  const [toolId, setToolId] = useState("");
  const [bindingKey, setBindingKey] = useState("");
  const selected = data?.tools.find((tool) => tool.id === toolId);
  function bind(version: ToolVersion) {
    const key = bindingKey.trim() || selected?.name || "";
    if (!/^[a-z][a-z0-9_]*$/.test(key)) {
      toast.error(
        "Binding name must be lowercase letters, digits or underscores",
      );
      return;
    }
    if (!selected) return;
    change({
      ...config,
      tool_bindings: {
        ...config.tool_bindings,
        [key]: { tool_id: selected.id, tool_version_id: version.id },
      },
    });
    toast.success(`Bound ${key} in draft. Save to persist.`);
  }
  function unbind(key: string) {
    const bindings = { ...config.tool_bindings };
    delete bindings[key];
    change({
      ...config,
      tool_bindings: bindings,
      background_hooks: config.background_hooks.filter((name) => name !== key),
      flow: {
        ...config.flow,
        global_functions: (config.flow.global_functions ?? []).filter(
          (name) => name.name !== key,
        ),
        nodes: config.flow.nodes.map((node) => ({
          ...node,
          tool_bindings: node.tool_bindings.filter((name) => name !== key),
          entry_actions: node.entry_actions.filter((name) => name !== key),
          exit_actions: node.exit_actions.filter((name) => name !== key),
          pre_actions: node.pre_actions.filter(
            (action) => action.type !== "function" || action.handler !== key,
          ),
          post_actions: node.post_actions.filter(
            (action) => action.type !== "function" || action.handler !== key,
          ),
        })),
      },
    });
  }
  return (
    <section className="flex max-w-3xl flex-col gap-7">
      <div>
        <h2 className="mb-2 text-base font-semibold">Pinned tool versions</h2>
        {Object.entries(config.tool_bindings).length ? (
          Object.entries(config.tool_bindings).map(([key, binding]) => (
            <div
              key={key}
              className="flex items-center justify-between gap-2 border-b py-2 text-sm"
            >
              <div>
                <strong>{key}</strong>
                <div>
                  <CopyId label="Tool ID" value={binding.tool_id} />
                </div>
                <div>
                  <CopyId
                    label="Tool Version ID"
                    value={binding.tool_version_id}
                  />
                </div>
              </div>
              {!disabled && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => unbind(key)}
                >
                  Remove
                </Button>
              )}
            </div>
          ))
        ) : (
          <p className="text-sm text-muted-foreground">
            No tool versions bound. Node tool lists stay empty.
          </p>
        )}
      </div>
      {!disabled && (
        <div className="flex flex-col gap-4 border-t pt-5">
          <h2 className="text-base font-semibold">Add binding</h2>
          <LoadState
            loading={loading}
            error={error}
            empty={
              data?.tools.length === 0
                ? "No registered tools. Create and publish one under Tools."
                : undefined
            }
          >
            <FieldGroup>
              <Field>
                <FieldLabel htmlFor="tool-catalog">Tool</FieldLabel>
                <NativeSelect
                  id="tool-catalog"
                  value={toolId}
                  onChange={(event) => {
                    setToolId(event.target.value);
                    setBindingKey(
                      data?.tools.find((tool) => tool.id === event.target.value)
                        ?.name ?? "",
                    );
                  }}
                >
                  <option value="">Select tool</option>
                  {data?.tools.map((tool) => (
                    <option key={tool.id} value={tool.id}>
                      {tool.name}
                    </option>
                  ))}
                </NativeSelect>
              </Field>
              <Field>
                <FieldLabel htmlFor="binding-key">
                  Agent binding name
                </FieldLabel>
                <Input
                  id="binding-key"
                  value={bindingKey}
                  onChange={(event) => setBindingKey(event.target.value)}
                  placeholder="change_node"
                />
              </Field>
            </FieldGroup>
            {selected && <VersionPicker tool={selected} onBind={bind} />}
          </LoadState>
        </div>
      )}
      <ReadOnlyValue
        label="Background hooks"
        value={config.background_hooks.join(", ") || "None"}
        reason="Hook editing needs runtime-safe trigger validation."
      />
      <p className="text-xs text-muted-foreground">
        Bound tools become selectable per flow node. Binding a tool does not
        itself grant a node access.
      </p>
    </section>
  );
}
