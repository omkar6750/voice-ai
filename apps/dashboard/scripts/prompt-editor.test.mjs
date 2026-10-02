import test, { after, afterEach } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { readFileSync } from "node:fs";
const classifierContract = JSON.parse(
  readFileSync(
    new URL("./lead-classifier-contract.fixture.json", import.meta.url),
    "utf8",
  ),
);
import { JSDOM } from "jsdom";
import { createServer } from "vite";

// DOM/model checks, not browser automation; no API or provider requests.
const dom = new JSDOM("<!doctype html><html><body></body></html>", {
  url: "http://localhost/",
});
for (const key of [
  "window",
  "document",
  "HTMLElement",
  "Element",
  "Node",
  "NodeFilter",
  "MutationObserver",
  "getComputedStyle",
  "Event",
  "KeyboardEvent",
  "MouseEvent",
  "CustomEvent",
  "DocumentFragment",
  "HTMLButtonElement",
  "HTMLInputElement",
  "FocusEvent",
])
  globalThis[key] = dom.window[key];
Object.defineProperty(globalThis, "navigator", {
  value: dom.window.navigator,
  configurable: true,
});
globalThis.requestAnimationFrame = (callback) => setTimeout(callback, 0);
globalThis.cancelAnimationFrame = clearTimeout;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
// jsdom has no layout engine. Selection geometry is deliberately not asserted.
dom.window.Range.prototype.getClientRects = () => [];
dom.window.Range.prototype.getBoundingClientRect = () => ({
  left: 0,
  right: 0,
  top: 0,
  bottom: 0,
});
const React = await import("react");
const { render, screen, fireEvent, waitFor, act, cleanup } =
  await import("@testing-library/react");
const { Editor } = await import("@tiptap/core");
const { UndoRedo } = await import("@tiptap/extensions");
const { TextSelection } = await import("@tiptap/pm/state");
const vite = await createServer({
  configFile: false,
  root: fileURLToPath(new URL("../", import.meta.url)),
  resolve: {
    alias: { "@": fileURLToPath(new URL("../src", import.meta.url)) },
  },
  esbuild: { jsx: "automatic" },
  optimizeDeps: { noDiscovery: true, include: [] },
  server: { middlewareMode: true, hmr: false },
  appType: "custom",
});
const { promptDocument, promptExtensions } = await vite.ssrLoadModule(
  "/src/pages/agents/prompt-document.ts",
);
const { PromptEditor } = await vite.ssrLoadModule(
  "/src/pages/agents/PromptEditor.tsx",
);
const { FlowPanel } = await vite.ssrLoadModule(
  "/src/pages/agents/FlowPanel.tsx",
);
const { reorderFlowNodes } = await vite.ssrLoadModule(
  "/src/pages/agents/FlowWorkspace.tsx",
);
const { LeadClassifierDetails } = await vite.ssrLoadModule(
  "/src/pages/agents/ClassifierPanel.tsx",
);
afterEach(cleanup);
after(async () => {
  await vite.close();
  dom.window.close();
});

test("literal prompt roundtrip, inline highlights, selection, newline, paste and undo", () => {
  const text =
    "  Hello {{ name }}\n\nCall #book_callback.\n中文 🙂 <strong>literal</strong>\n";
  const catalog = { tools: ["book_callback"], variables: ["name"] };
  const editor = new Editor({
    element: document.createElement("div"),
    extensions: [...promptExtensions(() => catalog), UndoRedo],
    content: promptDocument(text),
  });
  assert.equal(editor.getText(), text);
  assert.equal(
    editor.view.dom.querySelectorAll("[data-prompt-reference]").length,
    2,
  );
  assert.deepEqual(editor.getJSON(), promptDocument(text));
  editor.commands.setTextSelection({ from: 3, to: 8 });
  editor.commands.insertContent({ type: "text", text: "{{ name }}" });
  assert.equal(
    editor.getText(),
    text.slice(0, 2) + "{{ name }}" + text.slice(7),
  );
  assert.equal(editor.state.selection.from, 13);
  assert.ok(editor.commands.undo());
  assert.equal(editor.getText(), text);
  assert.ok(editor.commands.redo());
  editor.commands.setTextSelection(1);
  assert.ok(editor.commands.keyboardShortcut("Enter"));
  assert.ok(editor.getText().startsWith("\n  "));
  const event = {
    clipboardData: {
      getData: (type) =>
        type === "text/plain" ? "plain\r\n{{ name }}" : "<b>bold</b>",
    },
  };
  editor.view.someProp("handlePaste", (handler) => handler(editor.view, event));
  assert.ok(editor.getText().includes("plain\n{{ name }}"));
  const pos = editor.state.selection.from;
  catalog.variables = [];
  editor.view.dispatch(editor.state.tr.setMeta("prompt-catalog", true));
  assert.equal(editor.state.selection.from, pos);
  assert.equal(
    editor.view.dom.querySelector('[data-prompt-reference="variable"]').title,
    "Unbound reference",
  );
  editor.commands.selectAll();
  editor.commands.deleteSelection();
  assert.equal(editor.getText(), "");
  assert.equal(editor.state.doc.childCount, 1);
  editor.destroy();
});

test("controlled parent echo retains cursor; buttons insert there; external load and disabled state apply", async () => {
  let change;
  function Harness({ disabled = false, initial = "Before after" }) {
    const [value, setValue] = React.useState(initial);
    change = setValue;
    return React.createElement(PromptEditor, {
      id: "test-prompt",
      label: "Prompt",
      value,
      onChange: setValue,
      availableTools: ["book_callback"],
      registeredTools: [],
      availableVariables: ["name"],
      disabled,
    });
  }
  const ui = render(React.createElement(Harness));
  const input = await screen.findByRole("textbox", { name: "Prompt" });
  assert.equal(document.querySelector("textarea"), null);
  const view = input.editor.view;
  await act(async () =>
    view.dispatch(
      view.state.tr.setSelection(TextSelection.create(view.state.doc, 8)),
    ),
  );
  fireEvent.mouseDown(screen.getByRole("button", { name: /\{\{ name \}\}/ }));
  fireEvent.click(screen.getByRole("button", { name: /\{\{ name \}\}/ }));
  await waitFor(() =>
    assert.equal(input.textContent, "Before {{ name }}after"),
  );
  assert.equal(view.state.selection.from, 18);
  fireEvent.mouseDown(screen.getByRole("button", { name: "#book_callback" }));
  fireEvent.click(screen.getByRole("button", { name: "#book_callback" }));
  await waitFor(() =>
    assert.equal(input.textContent, "Before {{ name }}#book_callbackafter"),
  );
  await act(async () => change("Loaded\n\n{{ name }}"));
  assert.equal(input.textContent, "Loaded\n\n{{ name }}");
  const instance = input.editor;
  fireEvent.click(screen.getByRole("button", { name: "Expand Prompt" }));
  await screen.findByRole("dialog", { name: "Prompt" });
  const expanded = screen.getByRole("textbox", { name: "Prompt" });
  assert.equal(expanded.editor, instance);
  await act(async () =>
    instance.commands.insertContent({ type: "text", text: " expanded edit" }),
  );
  const expandedText = instance.getText();
  fireEvent.keyDown(document, { key: "Escape", code: "Escape" });
  await waitFor(() => assert.equal(screen.queryByRole("dialog"), null));
  assert.equal(
    screen.getByRole("textbox", { name: "Prompt" }).editor,
    instance,
  );
  assert.equal(instance.getText(), expandedText);
  await act(async () => instance.commands.undo());
  assert.equal(instance.getText(), "Loaded\n\n{{ name }}");
  ui.rerender(React.createElement(Harness, { disabled: true }));
  await waitFor(() =>
    assert.equal(input.getAttribute("contenteditable"), "false"),
  );
  assert.equal(
    screen.getByRole("button", { name: /\{\{ name \}\}/ }).disabled,
    true,
  );
});

test("changing prompt/node identity cannot access a destroyed editor", async () => {
  const props = {
    label: "Node prompt",
    onChange: () => {},
    availableTools: [],
    registeredTools: [],
    availableVariables: [],
  };
  const node = (id, value, placeholder) =>
    React.createElement(
      React.StrictMode,
      null,
      React.createElement(PromptEditor, { ...props, id, value, placeholder }),
    );
  const ui = render(
    node("node-first", "First saved prompt", "First placeholder"),
  );
  await screen.findByRole("textbox", { name: "Node prompt" });
  ui.rerender(node("node-second", "Second saved prompt", "Second placeholder"));
  await waitFor(() =>
    assert.equal(
      screen.getByRole("textbox", { name: "Node prompt" }).textContent,
      "Second saved prompt",
    ),
  );
  ui.rerender(node("node-third", "Third saved prompt", "Third placeholder"));
  await waitFor(() =>
    assert.equal(
      screen.getByRole("textbox", { name: "Node prompt" }).textContent,
      "Third saved prompt",
    ),
  );
});

function flowFixture() {
  const node = (id, transitions, terminal = false) => ({
    id,
    role_message: `Prompt for ${id}`,
    task_messages: [{ role: "user", content: "Keep this task" }],
    functions: [],
    pre_actions: [],
    post_actions: [],
    prompt: "",
    role_prompt: null,
    context_strategy: "append",
    transitions,
    tool_bindings: [],
    entry_actions: [],
    exit_actions: [],
    respond_immediately: true,
    terminal,
  });
  return {
    system_prompt: "Global instructions",
    contact_variables: [],
    tool_bindings: {},
    fact_slots: [],
    classifier: { node_entries: [], node_exits: [] },
    flow: {
      initial_node: "greeting",
      global_functions: [],
      nodes: [
        node("greeting", ["discovery"]),
        node("discovery", ["closing"]),
        node("closing", [], true),
      ],
    },
  };
}
test("node reorder changes only list order and preserves node content and routing", () => {
  const cfg = flowFixture(),
    original = JSON.stringify(cfg);
  const next = reorderFlowNodes(cfg.flow.nodes, "greeting", "closing");
  assert.deepEqual(
    next.map((n) => n.id),
    ["discovery", "closing", "greeting"],
  );
  assert.equal(next[2], cfg.flow.nodes[0]);
  assert.equal(JSON.stringify(cfg), original);
  assert.deepEqual(next[2].transitions, ["discovery"]);
  assert.equal(reorderFlowNodes(next, "missing", "closing"), next);
});
test("flow workspace exposes node prompt, grouped settings and task messages without losing edits", async () => {
  let latest;
  function Harness({ disabled = false }) {
    const [config, setConfig] = React.useState(flowFixture);
    latest = config;
    return React.createElement(FlowPanel, {
      config,
      change: setConfig,
      registeredTools: [],
      disabled,
    });
  }
  const ui = render(React.createElement(Harness));
  const prompt = await screen.findByRole("textbox", {
    name: "System instruction (role_message)",
  });
  assert.equal(prompt.textContent, "Prompt for greeting");
  assert.ok(screen.getByRole("complementary", { name: "Node settings" }));
  assert.ok(screen.getByRole("button", { name: "Reorder node greeting" }));
  const context = screen.getByLabelText("Context strategy");
  fireEvent.change(context, { target: { value: "reset" } });
  assert.equal(latest.flow.nodes[0].context_strategy, "reset");
  fireEvent.mouseDown(screen.getByRole("tab", { name: "Task messages" }), {
    button: 0,
    ctrlKey: false,
  });
  fireEvent.click(screen.getByRole("tab", { name: "Task messages" }));
  await screen.findByLabelText("Task message 1 content");
  fireEvent.change(screen.getByLabelText("Task message 1 content"), {
    target: { value: "Updated task" },
  });
  assert.equal(latest.flow.nodes[0].task_messages[0].content, "Updated task");
  fireEvent.click(screen.getByRole("button", { name: "Next node" }));
  assert.equal(
    screen.getByLabelText("Task message 1 content").value,
    "Keep this task",
  );
  assert.equal(latest.flow.nodes[0].task_messages[0].content, "Updated task");
  fireEvent.click(screen.getByRole("button", { name: /Tools/ }));
  assert.ok(
    screen.getByText(
      "No published tools are connected yet. Connect one in the Tools tab.",
    ),
  );
  ui.rerender(React.createElement(Harness, { disabled: true }));
  assert.equal(
    screen.getByRole("button", { name: "Reorder node greeting" }).disabled,
    true,
  );
  assert.equal(screen.getByLabelText("Context strategy").disabled, true);
});

test("enabled node tools can be given result routing without duplicate exposure", async () => {
  let latest;
  function Harness() {
    const [config, setConfig] = React.useState(() => {
      const cfg = flowFixture();
      cfg.tool_bindings = { classify_lead: {} };
      cfg.flow.nodes[0].tool_bindings = ["classify_lead"];
      cfg.flow.nodes[0].functions = [
        {
          name: "go_to_discovery",
          transition_only: true,
          transition_to: "discovery",
        },
      ];
      return cfg;
    });
    latest = config;
    return React.createElement(FlowPanel, {
      config,
      change: setConfig,
      registeredTools: ["classify_lead"],
      classifierContract,
      disabled: false,
    });
  }
  render(React.createElement(Harness));
  fireEvent.click(screen.getByRole("button", { name: /Tools/ }));
  const routing = screen.getByLabelText("Add tool routing");
  assert.ok(
    [...routing.options].some((option) => option.value === "classify_lead"),
  );
  fireEvent.change(routing, { target: { value: "classify_lead" } });
  assert.deepEqual(latest.flow.nodes[0].tool_bindings, []);
  assert.equal(latest.flow.nodes[0].functions[1].name, "classify_lead");
  assert.equal(latest.flow.nodes[0].functions[1].transition_only, false);
  assert.equal(
    [...routing.options].some((option) => option.value === "classify_lead"),
    false,
  );
  fireEvent.change(screen.getByLabelText("transition_to"), {
    target: { value: "__branch__" },
  });
  assert.equal(
    latest.flow.nodes[0].functions[1].transition_to.field,
    "classification_key",
  );
  assert.equal(
    screen.getAllByRole("combobox", { name: /^Destination for / }).length,
    27,
  );
  fireEvent.change(
    screen.getByLabelText("Destination for hot|strong_fit|receptive"),
    { target: { value: "discovery" } },
  );
  assert.equal(
    latest.flow.nodes[0].functions[1].transition_to.cases[
      "hot|strong_fit|receptive"
    ],
    "discovery",
  );
  assert.equal(latest.flow.nodes[0].functions[0].transition_to, "discovery");
  fireEvent.change(screen.getByLabelText("Classifier result field"), {
    target: { value: "tone" },
  });
  assert.equal(
    screen.getAllByRole("combobox", { name: /^Destination for / }).length,
    3,
  );
  assert.deepEqual(latest.flow.nodes[0].functions[1].transition_to.cases, {});
  fireEvent.change(screen.getByLabelText("Destination for resistant"), {
    target: { value: "closing" },
  });
  assert.equal(
    latest.flow.nodes[0].functions[1].transition_to.cases.resistant,
    "closing",
  );
});

test("classifier settings expose locked questions without prompt or question editing", () => {
  render(
    React.createElement(LeadClassifierDetails, {
      contract: classifierContract,
    }),
  );
  assert.ok(screen.getByRole("region", { name: "Fixed classifier contract" }));
  assert.equal(screen.queryByRole("button", { name: "Add Question" }), null);
  assert.equal(screen.queryByRole("button", { name: "Add Choice" }), null);
  assert.equal(screen.queryByLabelText("System prompt & instructions"), null);
  assert.ok(screen.getByText("lead_temperature"));
  assert.ok(screen.getByText("service_fit"));
  assert.ok(screen.getByText("tone"));
});
