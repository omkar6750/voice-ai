import { useState, type ReactNode } from "react";
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  KeyboardSensor,
  useSensor,
  useSensors,
  closestCenter,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  useSortable,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
  arrayMove,
} from "@dnd-kit/sortable";
import { GripVertical, ChevronDown, type LucideIcon } from "lucide-react";
import { cn } from "cn";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Collapsible,
  CollapsibleTrigger,
  CollapsibleContent,
} from "@/components/ui/collapsible";
import type { FlowNode } from "./types";

export function ConfigGroup({
  title,
  icon: Icon,
  summary,
  defaultOpen = false,
  children,
}: {
  title: string;
  icon: LucideIcon;
  summary?: string;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <Collapsible
      open={open}
      onOpenChange={setOpen}
      className="rounded-lg bg-editor-background/60"
    >
      <CollapsibleTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          className="h-auto w-full justify-between gap-2 px-3 py-3"
        >
          <span className="flex items-center gap-2">
            <span className="flex size-6 items-center justify-center rounded-md bg-primary/10 text-primary">
              <Icon className="size-3.5" />
            </span>
            {title}
          </span>
          <span className="flex items-center gap-2">
            {summary && <Badge variant="secondary">{summary}</Badge>}
            <ChevronDown
              className={cn(
                "size-4 transition-transform",
                open && "rotate-180",
              )}
            />
          </span>
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="flex flex-col gap-4 p-3">{children}</div>
      </CollapsibleContent>
    </Collapsible>
  );
}

export function reorderFlowNodes(
  nodes: FlowNode[],
  activeId: string,
  overId: string,
) {
  const from = nodes.findIndex((n) => n.id === activeId),
    to = nodes.findIndex((n) => n.id === overId);
  return from < 0 || to < 0 || from === to ? nodes : arrayMove(nodes, from, to);
}

export function NodeList({
  nodes,
  selectedId,
  initialId,
  disabled,
  select,
  reorder,
}: {
  nodes: FlowNode[];
  selectedId: string;
  initialId: string;
  disabled: boolean;
  select: (id: string) => void;
  reorder: (nodes: FlowNode[]) => void;
}) {
  const [activeId, setActiveId] = useState<string | null>(null);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  );
  function finish({ active, over }: DragEndEvent) {
    setActiveId(null);
    if (disabled || !over) return;
    const next = reorderFlowNodes(nodes, String(active.id), String(over.id));
    if (next !== nodes) reorder(next);
  }
  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      onDragStart={({ active }) => setActiveId(String(active.id))}
      onDragCancel={() => setActiveId(null)}
      onDragEnd={finish}
    >
      <SortableContext
        items={nodes.map((n) => n.id)}
        strategy={verticalListSortingStrategy}
      >
        <div className="flex flex-col gap-1">
          {nodes.map((node) => (
            <SortableNode
              key={node.id}
              node={node}
              selected={selectedId === node.id}
              initial={initialId === node.id}
              disabled={disabled}
              select={select}
            />
          ))}
        </div>
      </SortableContext>
      <DragOverlay>
        {activeId && (
          <div
            aria-hidden="true"
            className="flex items-center gap-3 rounded-lg border border-primary/30 bg-background p-4 text-sm font-medium shadow-lg"
          >
            <GripVertical className="size-4 text-primary" />
            <span className="truncate">{activeId}</span>
          </div>
        )}
      </DragOverlay>
    </DndContext>
  );
}

function SortableNode({
  node,
  selected,
  initial,
  disabled,
  select,
}: {
  node: FlowNode;
  selected: boolean;
  initial: boolean;
  disabled: boolean;
  select: (id: string) => void;
}) {
  const {
    attributes,
    listeners,
    setNodeRef,
    setActivatorNodeRef,
    isDragging,
    isOver,
  } = useSortable({ id: node.id, disabled });
  return (
    <div
      ref={setNodeRef}
      data-node-id={node.id}
      className={cn(
        "flex min-w-0 items-center gap-1 rounded-md p-0.5",
        selected && "bg-primary/10",
        isDragging && "opacity-40",
        isOver && !isDragging && "ring-2 ring-primary/50",
      )}
    >
      <Button
        ref={setActivatorNodeRef}
        {...attributes}
        {...listeners}
        type="button"
        variant="ghost"
        size="icon-sm"
        disabled={disabled}
        aria-label={`Reorder node ${node.id}`}
        className="shrink-0 touch-none cursor-grab active:cursor-grabbing"
      >
        <GripVertical />
      </Button>
      <Button
        type="button"
        variant="ghost"
        className="h-8 min-w-0 flex-1 justify-start gap-1 px-1"
        aria-current={selected ? "step" : undefined}
        onClick={() => select(node.id)}
      >
        <span className="min-w-0 truncate text-xs" title={node.id}>
          {node.id}
        </span>
        {(initial || node.terminal) && (
          <Badge variant="secondary" className="shrink-0 px-1.5 text-[10px]">
            {initial ? "Initial" : "Terminal"}
          </Badge>
        )}
      </Button>
    </div>
  );
}
