import type { AgentConfig, FlowNode } from "./types";

export function needsOpeningTask(node: FlowNode, initialId: string): boolean {
  return (
    node.id === initialId &&
    node.respond_immediately &&
    !node.task_messages.some(
      (message) => message.role === "user" && message.content.trim(),
    )
  );
}

export function openingTaskError(config: AgentConfig): string | null {
  const node = config.flow.nodes.find(
    (item) => item.id === config.flow.initial_node,
  );
  return node && needsOpeningTask(node, config.flow.initial_node)
    ? "The initial node responds on entry. Add a nonempty user task message in Flow > Task messages, or disable Responds on entry."
    : null;
}
