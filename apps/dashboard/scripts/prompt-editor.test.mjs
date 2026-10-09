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
const { ChatTranscriptEntry, ChatInspection, transcriptEntries } =
  await vite.ssrLoadModule("/src/pages/agents/ChatEvidence.tsx");

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

test("conversation fact state key retains focus through consecutive edits", () => {
  let latest;
  function Harness() {
    const [config, setConfig] = React.useState(flowFixture);
    latest = config;
    return React.createElement(FlowPanel, {
      config,
      change: setConfig,
      registeredTools: [],
      disabled: false,
    });
  }
  render(React.createElement(Harness));
  fireEvent.click(screen.getByRole("button", { name: /Conversation facts/ }));
  fireEvent.click(screen.getByRole("button", { name: "Add fact slot" }));
  const input = screen.getByDisplayValue(latest.fact_slots[0].key);
  input.focus();
  let value = "";
  for (const character of "caller_name") {
    value += character;
    fireEvent.change(input, { target: { value } });
    assert.equal(document.activeElement, input);
    assert.equal(screen.getByDisplayValue(value), input);
    assert.equal(latest.fact_slots[0].key, value);
  }
  assert.equal(latest.fact_slots[0].key, "caller_name");
});

test("generated fact tools appear immediately and follow node scopes, rename and deletion", async () => {
  let latest, update;
  function Harness() {
    const [config, setConfig] = React.useState(() => {
      const initial = flowFixture();
      initial.flow.nodes[0].role_message =
        "Save the name with #record_recepient_name";
      initial.flow.nodes[1].role_message =
        "Save the name with #record_recepient_name";
      return initial;
    });
    latest = config;
    update = setConfig;
    return React.createElement(FlowPanel, {
      config,
      change: setConfig,
      registeredTools: [],
      disabled: false,
    });
  }
  render(React.createElement(Harness));
  let prompt = await screen.findByRole("textbox", {
    name: "System instruction (role_message)",
  });
  assert.equal(prompt.getAttribute("aria-invalid"), "true");
  fireEvent.click(screen.getByRole("button", { name: /Conversation facts/ }));
  fireEvent.click(screen.getByRole("button", { name: "Add fact slot" }));
  fireEvent.change(screen.getByDisplayValue("caller_fact"), {
    target: { value: "recepient_name" },
  });
  await waitFor(() =>
    assert.equal(prompt.getAttribute("aria-invalid"), "false"),
  );
  const insert = screen.getByRole("button", { name: "#record_recepient_name" });
  fireEvent.click(insert);
  await waitFor(() =>
    assert.ok(
      latest.flow.nodes[0].role_message.endsWith("#record_recepient_name"),
    ),
  );
  assert.ok(
    prompt.querySelector('[data-prompt-reference="tool"]').title ===
      "Available tool",
  );
  await act(async () =>
    update({
      ...latest,
      fact_slots: latest.fact_slots.map((slot) => ({
        ...slot,
        nodes: ["greeting"],
      })),
    }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Next node" }));
  prompt = await screen.findByRole("textbox", {
    name: "System instruction (role_message)",
  });
  await waitFor(() =>
    assert.equal(prompt.getAttribute("aria-invalid"), "true"),
  );
  assert.equal(
    screen.queryByRole("button", { name: "#record_recepient_name" }),
    null,
  );
  await act(async () =>
    update({
      ...latest,
      fact_slots: latest.fact_slots.map((slot) => ({ ...slot, nodes: [] })),
    }),
  );
  await waitFor(() =>
    assert.equal(prompt.getAttribute("aria-invalid"), "false"),
  );
  fireEvent.change(screen.getByDisplayValue("recepient_name"), {
    target: { value: "recipient_name" },
  });
  await waitFor(() =>
    assert.ok(screen.getByRole("button", { name: "#record_recipient_name" })),
  );
  assert.equal(
    screen.queryByRole("button", { name: "#record_recepient_name" }),
    null,
  );
  assert.equal(prompt.getAttribute("aria-invalid"), "true");
  fireEvent.click(
    screen.getByRole("button", { name: "Remove fact slot recipient_name" }),
  );
  assert.equal(
    screen.queryByRole("button", { name: "#record_recipient_name" }),
    null,
  );
});

test("global prompt recognizes configured generated fact tools", async () => {
  const { PromptsPanel } = await vite.ssrLoadModule(
    "/src/pages/agents/PromptsPanel.tsx",
  );
  const cfg = flowFixture();
  cfg.language = { default_language: "en", supported_languages: ["en"] };
  cfg.idle_reprompt_text = "";
  cfg.idle_reprompt_limit = 1;
  cfg.system_prompt = "Use #record_recipient_name when they give their name.";
  cfg.fact_slots = [
    {
      key: "recipient_name",
      description: "Caller name",
      value_type: "string",
      nodes: ["greeting"],
    },
  ];
  render(
    React.createElement(PromptsPanel, {
      config: cfg,
      change: () => {},
      boundTools: [],
      registeredTools: [],
      disabled: false,
    }),
  );
  const prompt = await screen.findByRole("textbox", {
    name: "Global system instruction",
  });
  await waitFor(() =>
    assert.equal(prompt.getAttribute("aria-invalid"), "false"),
  );
  assert.ok(screen.getByRole("button", { name: "#record_recipient_name" }));
});

test("saved fact variables remain readable in nodes without the recording tool", async () => {
  const cfg = flowFixture();
  cfg.fact_slots = [
    {
      key: "recepient_name",
      description: "Caller name",
      value_type: "string",
      nodes: ["greeting"],
    },
  ];
  cfg.flow.nodes[1].role_message = "Confirmed caller name: {{recepient_name}}";
  render(
    React.createElement(FlowPanel, {
      config: cfg,
      change: () => {},
      registeredTools: [],
      disabled: false,
    }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Next node" }));
  const prompt = await screen.findByRole("textbox", {
    name: "System instruction (role_message)",
  });
  await waitFor(() =>
    assert.equal(prompt.getAttribute("aria-invalid"), "false"),
  );
  assert.ok(screen.getByRole("button", { name: /recepient_name/ }));
  assert.equal(
    screen.queryByRole("button", { name: "#record_recepient_name" }),
    null,
  );
});

test("generated go-to references follow the node direct transition settings", async () => {
  let latest, update;
  function Harness() {
    const [config, setConfig] = React.useState(() => {
      const cfg = flowFixture();
      cfg.flow.nodes[0].role_message = "If refused, call #go_to_closing.";
      cfg.flow.nodes[0].transitions = ["closing"];
      return cfg;
    });
    latest = config;
    update = setConfig;
    return React.createElement(FlowPanel, {
      config,
      change: setConfig,
      registeredTools: [],
      disabled: false,
    });
  }
  render(React.createElement(Harness));
  const prompt = await screen.findByRole("textbox", {
    name: "System instruction (role_message)",
  });
  await waitFor(() =>
    assert.equal(prompt.getAttribute("aria-invalid"), "false"),
  );
  assert.ok(screen.getByRole("button", { name: "#go_to_closing" }));
  await act(async () =>
    update({
      ...latest,
      flow: {
        ...latest.flow,
        nodes: latest.flow.nodes.map((node, index) =>
          index === 0 ? { ...node, transitions: [] } : node,
        ),
      },
    }),
  );
  await waitFor(() =>
    assert.equal(prompt.getAttribute("aria-invalid"), "true"),
  );
  assert.equal(screen.queryByRole("button", { name: "#go_to_closing" }), null);
});

test("routed tool chips reflect availability and toggle routed functions", async () => {
  let latest;
  function Harness() {
    const [config, setConfig] = React.useState(() => {
      const cfg = flowFixture();
      cfg.tool_bindings = { classify_lead: {} };
      cfg.flow.nodes[0].functions = [
        { name: "classify_lead", transition_only: false, transition_to: null },
      ];
      return cfg;
    });
    latest = config;
    return React.createElement(FlowPanel, {
      config,
      change: setConfig,
      registeredTools: [],
      disabled: false,
    });
  }
  render(React.createElement(Harness));
  fireEvent.click(screen.getByRole("button", { name: /^Tools/ }));
  const chip = screen.getByRole("button", { name: "classify_lead" });
  assert.equal(chip.getAttribute("aria-pressed"), "true");
  assert.equal(chip.getAttribute("data-variant"), "secondary");
  fireEvent.click(chip);
  assert.equal(chip.getAttribute("aria-pressed"), "false");
  assert.equal(chip.getAttribute("data-variant"), "choice");
  assert.equal(latest.flow.nodes[0].functions.length, 0);
  fireEvent.click(chip);
  assert.deepEqual(latest.flow.nodes[0].tool_bindings, ["classify_lead"]);
});

test("shared classifier routing can be cleared and availability disabled", async () => {
  let latest;
  function Harness() {
    const [config, setConfig] = React.useState(() => {
      const cfg = flowFixture();
      cfg.tool_bindings = { classify_lead: {} };
      cfg.flow.global_functions = [
        {
          name: "classify_lead",
          transition_only: false,
          transition_to: "discovery",
        },
      ];
      return cfg;
    });
    latest = config;
    return React.createElement(FlowPanel, {
      config,
      change: setConfig,
      registeredTools: [],
      disabled: false,
    });
  }
  render(React.createElement(Harness));
  fireEvent.click(screen.getByRole("button", { name: /^Shared tools/ }));
  const chip = screen.getByRole("button", { name: "classify_lead" });
  assert.equal(chip.getAttribute("aria-pressed"), "true");
  fireEvent.click(screen.getByRole("button", { name: "Clear shared routing" }));
  assert.equal(latest.flow.global_functions[0].transition_to, null);
  assert.equal(
    screen.getByLabelText("Shared classifier routing mode").value,
    "__stay__",
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Disable shared tool classify_lead" }),
  );
  assert.deepEqual(latest.flow.global_functions, []);
  assert.equal(chip.getAttribute("aria-pressed"), "false");
  assert.equal(chip.getAttribute("data-variant"), "choice");
  assert.equal(screen.queryByLabelText("Shared classifier routing mode"), null);
});

test("chat shows one completed tool call and opens its actual evidence", () => {
  const entries = [
    {
      id: "start",
      run_id: "run",
      sequence: 1,
      kind: "evidence",
      saved: true,
      payload: {
        kind: "tool_started",
        invocation_id: "fact",
        binding_key: "record_caller_name",
        started_ns: 1000000,
      },
    },
    {
      id: "end",
      run_id: "run",
      sequence: 2,
      kind: "evidence",
      saved: true,
      payload: {
        kind: "tool_ended",
        invocation_id: "fact",
        status: "completed",
        ended_ns: 6000000,
      },
    },
  ];
  const visible = transcriptEntries(entries);
  assert.equal(visible.length, 1);
  let selected;
  render(
    React.createElement(ChatTranscriptEntry, {
      entry: visible[0],
      entries,
      inspect: (e) => {
        selected = e;
      },
    }),
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Inspect record_caller_name details" }),
  );
  assert.equal(selected.id, "end");
  assert.ok(screen.getByText(/Called record_caller_name/));
  assert.ok(screen.getByText(/5 ms/));
});
test("chat inspector reports actual model usage and separates missing metrics", () => {
  render(
    React.createElement(ChatInspection, {
      value: {
        message: { kind: "span" },
        operations: [
          {
            id: "llm",
            name: "inference",
            category: "llm",
            model: "test-model",
            provider: "test-provider",
            status: "completed",
            duration_ms: 45,
            prompt_tokens: 12,
            completion_tokens: 3,
            total_tokens: 15,
            input_payload: { messages: [] },
            output_payload: { text: "Hello" },
          },
          {
            id: "summary",
            name: "summary",
            category: "summarizer",
            status: "completed",
          },
        ],
      },
    }),
  );
  assert.ok(screen.getByText("test-model"));
  assert.ok(screen.getByText("45 ms"));
  assert.ok(screen.getByText("12"));
  assert.ok(screen.getByText("3"));
  assert.ok(screen.getByText("15"));
  assert.ok(screen.getAllByText("Not reported").length);
});

test("chat distinguishes agent classifier calls from automatic cadence", () => {
  const tool = {
    id: "tool",
    run_id: "run",
    sequence: 1,
    kind: "evidence",
    payload: {
      kind: "tool_started",
      invocation_id: "classifier-tool",
      binding_key: "classify_lead",
    },
  };
  const automatic = {
    id: "auto",
    run_id: "run",
    sequence: 2,
    kind: "evidence",
    payload: {
      kind: "classifier_result",
      phase: "cadence",
      status: "completed",
    },
  };
  render(
    React.createElement(
      React.Fragment,
      null,
      React.createElement(ChatTranscriptEntry, {
        entry: tool,
        entries: [tool, automatic],
        inspect: () => {},
      }),
      React.createElement(ChatTranscriptEntry, {
        entry: automatic,
        entries: [tool, automatic],
        inspect: () => {},
      }),
    ),
  );
  assert.ok(screen.getByText("Agent called classifier tool"));
  assert.ok(
    screen.getByRole("button", {
      name: "Automatic classifier (cadence) - completed",
    }),
  );
});

const { parsePrompt, promptErrors } = await vite.ssrLoadModule(
  "/src/pages/agents/prompt-templates.ts",
);
const { FactDefault } = await vite.ssrLoadModule(
  "/src/pages/agents/FactDefault.tsx",
);

test("fallback parser agrees with shared backend fixtures", () => {
  const fixtures = JSON.parse(
    readFileSync(
      new URL(
        "../../../contracts/prompt-template-fixtures.json",
        import.meta.url,
      ),
      "utf8",
    ),
  );
  for (const fixture of fixtures) {
    if (fixture.error) assert.throws(() => parsePrompt(fixture.text));
    else assert.deepEqual(parsePrompt(fixture.text), fixture.tokens);
  }
  assert.match(
    promptErrors("[ {{a}} | {{b}} ]", ["a", "b"], ["b"])[0],
    /Boolean/,
  );
});

test("fallback groups preserve literal text, paste, edits and undo", () => {
  const text =
    "Speak [ {{language}} | {{confirmed}} ].\n[ {{language}} | {{flag}} ]";
  const catalog = {
    tools: [],
    variables: ["language", "confirmed", "flag"],
    booleans: ["flag"],
  };
  const editor = new Editor({
    element: document.createElement("div"),
    extensions: [...promptExtensions(() => catalog), UndoRedo],
    content: promptDocument(text),
  });
  assert.equal(editor.getText(), text);
  assert.equal(
    editor.view.dom.querySelectorAll("[data-prompt-expression-start]").length,
    2,
  );
  for (const group of editor.view.dom.querySelectorAll(
    '[data-prompt-reference="fallback"]',
  )) {
    assert.equal(
      group.querySelectorAll('[data-prompt-reference="variable"]').length,
      0,
    );
  }
  assert.ok(
    editor.view.dom
      .querySelector('[data-prompt-reference="fallback"]')
      .classList.contains("bg-primary/15"),
  );
  assert.ok(editor.view.dom.querySelector('[title*="Boolean"]'));
  editor.commands.setTextSelection(1);
  editor.commands.insertContent({
    type: "text",
    text: "[ {{confirmed}} | {{language}} ]\n",
  });
  assert.ok(editor.commands.undo());
  assert.equal(editor.getText(), text);
  assert.ok(editor.commands.redo());
  assert.ok(editor.getText().startsWith("[ {{confirmed}} | {{language}} ]\n"));
  editor.destroy();
});

test("fallback Unicode decoration uses document positions", () => {
  const text = "🙂 [ {{language}} | {{confirmed}} ]";
  const editor = new Editor({
    element: document.createElement("div"),
    extensions: promptExtensions(() => ({
      tools: [],
      variables: ["language", "confirmed"],
    })),
    content: promptDocument(text),
  });
  const highlighted = Array.from(
    editor.view.dom.querySelectorAll("[data-prompt-expression-start]"),
  )
    .map((element) => element.textContent)
    .join("");
  assert.equal(highlighted, "[ {{language}} | {{confirmed}} ]");
  assert.equal(editor.getText(), text);
  editor.destroy();
});

test("fallback picker inserts ordered variables and excludes booleans", async () => {
  let latest = "";
  render(
    React.createElement(PromptEditor, {
      id: "fallback-test",
      label: "Prompt",
      value: "",
      onChange: (value) => {
        latest = value;
      },
      availableTools: [],
      registeredTools: [],
      availableVariables: ["language", "confirmed", "flag"],
      booleanVariables: ["flag"],
    }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Insert fallback" }));
  const second = screen.getByRole("combobox", { name: "Fallback variable 2" });
  assert.ok(!Array.from(second.options).some((o) => o.value === "flag"));
  fireEvent.change(second, { target: { value: "confirmed" } });
  fireEvent.click(screen.getByRole("button", { name: "Add variable" }));
  fireEvent.change(
    screen.getByRole("combobox", { name: "Fallback variable 3" }),
    { target: { value: "confirmed" } },
  );
  fireEvent.click(screen.getAllByRole("button", { name: "Move earlier" })[2]);
  fireEvent.click(screen.getByRole("button", { name: "Insert expression" }));
  await waitFor(() =>
    assert.equal(latest, "[ {{language}} | {{confirmed}} | {{confirmed}} ]"),
  );
});

test("prompt preview sends unsaved samples and explains empty resolution", async () => {
  const { PromptPreview } = await vite.ssrLoadModule(
    "/src/pages/agents/PromptPreview.tsx",
  );
  const { ApiContext } = await vite.ssrLoadModule("/src/app/api.ts");
  const config = flowFixture();
  config.contact_variables = ["language"];
  config.fact_slots = [
    { key: "confirmed", value_type: "string", default_value: "" },
  ];
  config.system_prompt = "Speak [ {{language}} | {{confirmed}} ].";
  const calls = [];
  const api = async (path, init) => {
    const body = JSON.parse(init.body);
    calls.push({ path, method: init.method, body });
    return {
      rendered: { role_message: "Speak ." },
      resolution: [
        {
          field: "role_message",
          start: 6,
          expression: "[ {{language}} | {{confirmed}} ]",
          outcome: "all_empty",
          selected_key: null,
          value: "",
          candidates: [
            {
              key: "language",
              value: "",
              empty_reason: "empty_string",
              source: { kind: "contact" },
            },
          ],
        },
      ],
    };
  };
  render(
    React.createElement(
      ApiContext.Provider,
      { value: api },
      React.createElement(PromptPreview, {
        config,
        nodeId: "greeting",
        versionId: "draft-test",
      }),
    ),
  );
  fireEvent.change(
    screen.getByRole("textbox", { name: "Contact sample language" }),
    { target: { value: "mr-IN" } },
  );
  fireEvent.change(
    screen.getByRole("textbox", { name: "Fact sample confirmed" }),
    { target: { value: "hi-IN" } },
  );
  fireEvent.click(screen.getByRole("button", { name: "Render preview" }));
  await waitFor(() => assert.equal(calls.length, 1));
  assert.equal(calls[0].path, "/agent-versions/draft-test/prompt-preview");
  assert.equal(calls[0].method, "POST");
  assert.deepEqual(calls[0].body.contact_values, { language: "mr-IN" });
  assert.deepEqual(calls[0].body.fact_values, { confirmed: "hi-IN" });
  assert.equal(calls[0].body.config.system_prompt, config.system_prompt);
  await waitFor(() =>
    assert.ok(
      screen.getByText("All candidates empty; renders an empty string."),
    ),
  );
  fireEvent.click(screen.getByRole("button", { name: "Try all empty" }));
  await waitFor(() => assert.equal(calls.length, 2));
  assert.deepEqual(calls[1].body.contact_values, { language: "" });
  assert.deepEqual(calls[1].body.fact_values, { confirmed: "" });
});

test("fact defaults allow unset, typed zero and false without losing false", () => {
  let value;
  const slot = {
    key: "flag",
    description: "Fact",
    value_type: "boolean",
    default_value: "",
    enum: null,
    minimum: null,
    maximum: null,
    nodes: [],
  };
  const view = render(
    React.createElement(FactDefault, {
      slot,
      disabled: false,
      change: (v) => {
        value = v;
      },
    }),
  );
  fireEvent.change(
    screen.getByRole("combobox", { name: "Default mode for flag" }),
    { target: { value: "value" } },
  );
  assert.equal(value, false);
  view.rerender(
    React.createElement(FactDefault, {
      slot: { ...slot, default_value: false },
      disabled: false,
      change: (v) => {
        value = v;
      },
    }),
  );
  assert.equal(
    screen.getByRole("combobox", { name: "Default for flag" }).value,
    "false",
  );
  fireEvent.change(
    screen.getByRole("combobox", { name: "Default mode for flag" }),
    { target: { value: "unset" } },
  );
  assert.equal(value, "");
});
