import test, { after, afterEach } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { JSDOM } from "jsdom";
import { createServer } from "vite";

// DOM unit tests only: no browser or running backend is contacted.
const dom = new JSDOM("<!doctype html><html><body></body></html>", {
  url: "http://localhost/",
});
for (const key of [
  "window",
  "document",
  "HTMLElement",
  "HTMLInputElement",
  "HTMLTextAreaElement",
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
  "HTMLSelectElement",
])
  globalThis[key] = dom.window[key];
Object.defineProperty(globalThis, "navigator", {
  value: dom.window.navigator,
  configurable: true,
});
globalThis.requestAnimationFrame = (callback) => setTimeout(callback, 0);
globalThis.cancelAnimationFrame = clearTimeout;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const React = await import("react");
const { createElement: h } = React;
const { render, fireEvent, screen, waitFor, cleanup, act } =
  await import("@testing-library/react");
const { createMemoryRouter, RouterProvider, Routes, Route } =
  await import("react-router-dom");
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
const { ToolEditor } = await vite.ssrLoadModule(
  "/src/pages/tools/ToolEditor.tsx",
);
const { PublishDialog } = await vite.ssrLoadModule(
  "/src/pages/tools/PublishDialog.tsx",
);
const { ApiContext, ApiError } = await vite.ssrLoadModule("/src/app/api.ts");
const { parameterRows, parametersSchema } = await vite.ssrLoadModule(
  "/src/pages/tools/authoring.ts",
);
afterEach(cleanup);
after(async () => {
  await vite.close();
  dom.window.close();
});

const version = {
  id: "version-1",
  version: 1,
  revision: 1,
  status: "draft",
  config: {
    name: "finish_call",
    description: "Original",
    kind: "registered",
    handler: "end_call",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        reason: { type: "string", enum: ["done", "busy"], default: "done" },
        details: { type: "object", properties: { nested: { type: "string" } } },
      },
      required: ["reason"],
    },
  },
};
const noop = () => {};
function mountEditor(api, selected = version, extras = {}) {
  const editor = h(
    ApiContext.Provider,
    { value: api },
    h(ToolEditor, {
      version: selected,
      handlers: [],
      onSaved: noop,
      onConflict: noop,
      onSectionChange: noop,
      ...extras,
    }),
  );
  // Match the application's root data-router plus nested declarative routes.
  const router = createMemoryRouter(
    [
      {
        path: "*",
        element: h(
          Routes,
          null,
          h(Route, {
            path: "/tools/:toolId/versions/:versionId/edit",
            element: editor,
          }),
          h(Route, {
            path: "/elsewhere",
            element: h("p", null, "Destination"),
          }),
        ),
      },
    ],
    { initialEntries: ["/tools/tool-1/versions/version-1/edit"] },
  );
  const result = render(h(RouterProvider, { router }));
  return { router, result };
}

test("structured parameter editing retains nested schemas and constraints", () => {
  const original = version.config.parameters;
  const rows = parameterRows(original);
  assert.deepEqual(parametersSchema(rows, original), original);
  rows[0].name = "renamed_reason";
  const next = parametersSchema(rows, original);
  assert.deepEqual(next.properties.renamed_reason.enum, ["done", "busy"]);
  assert.deepEqual(next.properties.details, original.properties.details);
  assert.deepEqual(next.required, ["renamed_reason"]);
  assert.equal(next.additionalProperties, false);
  assert.throws(
    () => parametersSchema([{ ...rows[0], name: "" }], original),
    /name/,
  );
  assert.throws(() => parametersSchema([rows[0], rows[0]], original), /unique/);
});

test("advanced schema features and boolean properties survive structured round trips", () => {
  const schema = {
    type: "object",
    required: ["undeclared"],
    additionalProperties: false,
    $defs: { item: { type: "integer", minimum: 3 } },
    properties: {
      any: true,
      forbidden: false,
      ref: { $ref: "#/$defs/item" },
      union: { type: ["string", "null"] },
    },
  };
  assert.deepEqual(parametersSchema(parameterRows(schema), schema), schema);
  assert.deepEqual(parametersSchema([], { allOf: [{ type: "object" }] }), {
    allOf: [{ type: "object" }],
  });
});

test("saving remains in editor, preserves schema, and uses returned revision on next save", async () => {
  const calls = [];
  const api = async (path, init) => {
    calls.push({ path, body: JSON.parse(init.body) });
    return {
      id: version.id,
      revision: calls.length + 1,
      status: "draft",
      config: calls.at(-1).body.config,
    };
  };
  const { router } = mountEditor(api);
  fireEvent.change(
    screen.getByLabelText("When should the assistant use this tool?"),
    {
      target: { value: "Changed" },
    },
  );
  fireEvent.mouseDown(screen.getByRole("tab", { name: "Parameters" }), {
    button: 0,
    ctrlKey: false,
  });
  fireEvent.mouseDown(screen.getByRole("tab", { name: "Definition" }), {
    button: 0,
    ctrlKey: false,
  });
  assert.equal(
    screen.getByLabelText("When should the assistant use this tool?").value,
    "Changed",
  );
  fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
  await waitFor(() =>
    assert.match(screen.getByText(/Revision 2/).textContent, /Saved/),
  );
  assert.deepEqual(calls[0].body.config.parameters, version.config.parameters);
  assert.equal(
    router.state.location.pathname,
    "/tools/tool-1/versions/version-1/edit",
  );
  fireEvent.change(
    screen.getByLabelText("When should the assistant use this tool?"),
    {
      target: { value: "Changed again" },
    },
  );
  fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
  await waitFor(() => assert.equal(calls.length, 2));
  assert.equal(calls[1].body.revision, 2);
});

test("dirty validation saves first and validates the persisted configuration", async () => {
  const methods = [];
  const api = async (path, init) => {
    methods.push(init.method);
    if (init.method === "PATCH")
      return {
        id: version.id,
        revision: 2,
        config: JSON.parse(init.body).config,
      };
    return { id: version.id, revision: 2, valid: true, issues: [] };
  };
  mountEditor(api);
  fireEvent.change(
    screen.getByLabelText("When should the assistant use this tool?"),
    {
      target: { value: "Validate this" },
    },
  );
  fireEvent.click(screen.getByRole("button", { name: "Save & validate" }));
  await waitFor(() => assert.deepEqual(methods, ["PATCH", "POST"]));
});

test("a version published during editing retains unsaved input and blocks all writes", async () => {
  const selected = structuredClone(version);
  const requests = [];
  mountEditor(async (...args) => {
    requests.push(args);
  }, selected);
  fireEvent.change(
    screen.getByLabelText("When should the assistant use this tool?"),
    {
      target: { value: "Preserve after external publication" },
    },
  );
  selected.status = "published";
  fireEvent.mouseDown(screen.getByRole("tab", { name: "Parameters" }), {
    button: 0,
    ctrlKey: false,
  });
  fireEvent.mouseDown(screen.getByRole("tab", { name: "Definition" }), {
    button: 0,
    ctrlKey: false,
  });
  assert.equal(
    screen.getByLabelText("When should the assistant use this tool?").value,
    "Preserve after external publication",
  );
  assert.equal(
    screen
      .getByLabelText("When should the assistant use this tool?")
      .closest("fieldset").disabled,
    true,
  );
  assert.equal(
    screen.getByRole("button", { name: "Save draft" }).disabled,
    true,
  );
  assert.equal(
    screen.getByRole("button", { name: "Save & validate" }).disabled,
    true,
  );
  assert.equal(requests.length, 0);
});

test("navigation offers Stay and Discard; failed Save & leave preserves the editor", async () => {
  const { router } = mountEditor(async () => {
    throw new ApiError(409, "Draft changed by another operator");
  });
  fireEvent.change(
    screen.getByLabelText("When should the assistant use this tool?"),
    {
      target: { value: "Keep my work" },
    },
  );
  await act(async () => {
    await router.navigate("/elsewhere");
  });
  fireEvent.click(await screen.findByRole("button", { name: "Stay" }));
  assert.equal(
    router.state.location.pathname,
    "/tools/tool-1/versions/version-1/edit",
  );
  await act(async () => {
    await router.navigate("/elsewhere");
  });
  fireEvent.click(await screen.findByRole("button", { name: "Save & leave" }));
  await screen.findByText("This draft changed");
  await waitFor(() =>
    assert.equal(
      screen.getByLabelText("When should the assistant use this tool?").value,
      "Keep my work",
    ),
  );
  assert.equal(
    router.state.location.pathname,
    "/tools/tool-1/versions/version-1/edit",
  );
  fireEvent.click(screen.getByRole("button", { name: "Discard changes" }));
  await screen.findByText("Destination");
});

test("publication review blocks a revision different from the selected saved revision", async () => {
  const requests = [];
  const api = async (path) => {
    requests.push(path);
    return {
      id: version.id,
      revision: 2,
      valid: true,
      config: version.config,
      issues: [],
    };
  };
  render(
    h(
      ApiContext.Provider,
      { value: api },
      h(PublishDialog, {
        candidate: version,
        close: noop,
        onPublished: async () => {},
      }),
    ),
  );
  await screen.findByText("Publication blocked");
  assert.equal(
    screen.getByRole("button", { name: "Publish version" }).disabled,
    true,
  );
  assert.equal(requests.length, 1);
});

test("publication submits the reviewed revision once", async () => {
  const requests = [];
  const api = async (path, init) => {
    requests.push({ path, init });
    return path.endsWith("/validate")
      ? {
          id: version.id,
          revision: 1,
          valid: true,
          config: version.config,
          issues: [],
        }
      : { id: version.id, status: "published" };
  };
  render(
    h(
      ApiContext.Provider,
      { value: api },
      h(PublishDialog, {
        candidate: version,
        close: noop,
        onPublished: async () => {},
      }),
    ),
  );
  const button = screen.getByRole("button", { name: "Publish version" });
  await waitFor(() => assert.equal(button.disabled, false));
  fireEvent.click(button);
  await waitFor(() => assert.equal(requests.length, 2));
  assert.deepEqual(JSON.parse(requests[1].init.body), { revision: 1 });
});

test("merged WhatsApp controls preserve pinned connections and clear them when changing action", async () => {
  const selected = structuredClone(version);
  selected.config.handler = "send_whatsapp_message";
  selected.config.whatsapp_connection_id = "missing-connection";
  const calls = [];
  const api = async (path, init) => {
    const body = JSON.parse(init.body);
    calls.push(body);
    return { ...selected, revision: calls.length + 1, config: body.config };
  };
  mountEditor(api, selected, {
    handlers: [
      { name: "send_whatsapp_message", description: "Send a message" },
      { name: "end_call", description: "End the call" },
    ],
    whatsappConnections: [{ id: "enabled-connection", label: "Support WhatsApp" }],
  });
  fireEvent.mouseDown(screen.getByRole("tab", { name: "Execution" }), { button: 0, ctrlKey: false });
  const picker = screen.getByLabelText("whatsapp_connection_id");
  assert.equal(picker.value, "missing-connection");
  assert.ok(screen.getByRole("option", { name: "Pinned connection unavailable" }));
  fireEvent.change(picker, { target: { value: "enabled-connection" } });
  fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
  await waitFor(() => assert.equal(calls.length, 1));
  assert.equal(calls[0].config.whatsapp_connection_id, "enabled-connection");
  await waitFor(() => assert.equal(screen.getByLabelText("Approved backend action").disabled, false));
  fireEvent.change(screen.getByLabelText("Approved backend action"), { target: { value: "end_call" } });
  assert.equal(screen.queryByLabelText("whatsapp_connection_id"), null);
  fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
  await waitFor(() => assert.equal(calls.length, 2));
  assert.equal(calls[1].config.whatsapp_connection_id, null);
});