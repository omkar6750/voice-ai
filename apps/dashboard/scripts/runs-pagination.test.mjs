import test, { after, afterEach } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { JSDOM } from "jsdom";
import { createServer } from "vite";
const dom = new JSDOM("<!doctype html><html><body></body></html>", {
  url: "http://localhost/",
});
for (const key of [
  "window",
  "document",
  "HTMLElement",
  "HTMLInputElement",
  "HTMLSelectElement",
  "Element",
  "Node",
  "MutationObserver",
  "getComputedStyle",
  "Event",
])
  globalThis[key] = dom.window[key];
Object.defineProperty(globalThis, "navigator", {
  value: dom.window.navigator,
  configurable: true,
});
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { createElement: h } = await import("react");
const { render, fireEvent, screen, waitFor, cleanup, act } =
  await import("@testing-library/react");
const { MemoryRouter, Routes, Route } = await import("react-router-dom");
const { QueryClient, QueryClientProvider } =
  await import("@tanstack/react-query");
const vite = await createServer({
  configFile: false,
  root: fileURLToPath(new URL("../", import.meta.url)),
  resolve: {
    alias: { "@": fileURLToPath(new URL("../src", import.meta.url)) },
  },
  esbuild: { jsx: "automatic" },
  optimizeDeps: { noDiscovery: true, include: [] },
  plugins: [
    {
      name: "test-auth",
      enforce: "pre",
      transform(code, id) {
        if (
          id.replaceAll("\\", "/").endsWith("/pages/runs/index.tsx") ||
          id.replaceAll("\\", "/").endsWith("/lib/resources.ts")
        )
          return code.replace(
            'import { useAuth } from "@clerk/react";',
            "const useAuth = () => globalThis.__runsAuth;",
          );
      },
    },
  ],
  server: { middlewareMode: true, hmr: false },
  appType: "custom",
});
const { RunsPage } = await vite.ssrLoadModule("/src/pages/runs/index.tsx");
const { AgentEditorPage } = await vite.ssrLoadModule(
  "/src/pages/agents/AgentEditorPage.tsx",
);
const { OrganizationAccessContext } =
  await vite.ssrLoadModule("/src/app/access.ts");
const { ApiContext, request, ApiError } =
  await vite.ssrLoadModule("/src/app/api.ts");
let client;
afterEach(() => {
  cleanup();
  client?.clear();
});
after(async () => {
  await vite.close();
  dom.window.close();
});

test("actual runs page keeps pagination until filters change and clears cross-organization cursors", async () => {
  globalThis.__runsAuth = { userId: "user-1", orgId: "org-1" };
  const calls = [];
  const api = async (path, init) => {
    calls.push({ path, org: globalThis.__runsAuth.orgId, signal: init.signal });
    const page = new URL(path, "http://local").searchParams.get("cursor");
    return {
      runs: [
        {
          id: page ? "second" : "first",
          channel: "browser",
          transport_provider: "dashboard",
          agent_version_id: "version",
          status: "completed",
          created_at: "2026-10-01T00:00:00Z",
        },
      ],
      has_more: !page,
      next_cursor: page ? null : "cursor-one",
    };
  };
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const tree = () =>
    h(
      QueryClientProvider,
      { client },
      h(
        ApiContext.Provider,
        { value: api },
        h(MemoryRouter, null, h(RunsPage)),
      ),
    );
  const view = render(tree());
  await waitFor(() =>
    assert.ok(!screen.getByRole("button", { name: "Next" }).disabled),
  );
  fireEvent.click(screen.getByRole("button", { name: "Next" }));
  await waitFor(() => assert.ok(screen.getByText("second")));
  await act(() => new Promise((resolve) => setTimeout(resolve, 350)));
  assert.ok(screen.getByText("second"));
  assert.ok(calls.some((c) => c.path.includes("cursor=cursor-one")));
  assert.ok(calls.every((c) => c.signal instanceof AbortSignal));
  globalThis.__runsAuth = { userId: "user-1", orgId: "org-2" };
  view.rerender(tree());
  await waitFor(() => assert.ok(calls.some((c) => c.org === "org-2")));
  assert.ok(
    calls
      .filter((c) => c.org === "org-2")
      .every((c) => !c.path.includes("cursor=")),
  );
  await waitFor(() =>
    assert.ok(!screen.getByRole("button", { name: "Next" }).disabled),
  );
  fireEvent.click(screen.getByRole("button", { name: "Next" }));
  await waitFor(() => assert.ok(screen.getByText("second")));
  fireEvent.change(screen.getByRole("textbox", { name: "Search runs" }), {
    target: { value: "Ritu" },
  });
  await waitFor(() =>
    assert.ok(calls.some((c) => c.path.includes("search=Ritu"))),
  );
  assert.ok(
    calls
      .filter((c) => c.path.includes("search=Ritu"))
      .every((c) => !c.path.includes("cursor=")),
  );
  assert.ok(screen.getByRole("button", { name: "Previous" }).disabled);
});

test("version editor keeps local edits and refuses a silently advanced revision", async () => {
  globalThis.__runsAuth = { userId: "editor-user", orgId: "editor-org" };
  let version = {
    id: "version",
    agent_id: "agent",
    status: "draft",
    version: 1,
    revision: 1,
    note: "",
    config: {
      name: "Ritu",
      flow: { nodes: [] },
      tool_bindings: {},
      pipeline_logs: "inherit",
    },
  };
  const writes = [];
  const api = async (path, init) => {
    if (init?.method === "PATCH") {
      writes.push(JSON.parse(init.body));
      return version;
    }
    if (path === "/agent-versions/version") return version;
    if (path === "/tools") return { tools: [] };
    return {};
  };
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    h(
      QueryClientProvider,
      { client },
      h(
        ApiContext.Provider,
        { value: api },
        h(
          OrganizationAccessContext.Provider,
          { value: { canManage: true } },
          h(
            MemoryRouter,
            {
              initialEntries: [
                "/agents/agent/versions/version?section=logging",
              ],
            },
            h(
              Routes,
              null,
              h(Route, {
                path: "/agents/:agentId/versions/:versionId",
                element: h(AgentEditorPage),
              }),
            ),
          ),
        ),
      ),
    ),
  );
  const note = await screen.findByRole("textbox", { name: "Draft note" });
  fireEvent.change(note, { target: { value: "My unsaved changes" } });
  await act(async () => {
    client.setQueryData(
      [
        "resource",
        "editor-org",
        "no-support-session",
        "/agent-versions/version",
        "editor-user",
      ],
      { ...version },
    );
  });
  assert.equal(note.value, "My unsaved changes");
  version = { ...version, revision: 2, note: "Someone else's note" };
  await act(async () => {
    client.setQueryData(
      [
        "resource",
        "editor-org",
        "no-support-session",
        "/agent-versions/version",
        "editor-user",
      ],
      version,
    );
  });
  await waitFor(() =>
    assert.ok(
      screen.getByRole("alert").textContent.includes("Draft changed elsewhere"),
    ),
  );
  assert.equal(note.value, "My unsaved changes");
  assert.ok(screen.getByRole("button", { name: "Save changes" }).disabled);
  assert.equal(writes.length, 0);
});

test("API errors include field paths and the editor retains diagnostic details beside failed save", async () => {
  const originalFetch = globalThis.fetch;
  let failure;
  globalThis.fetch = async () =>
    new Response(
      JSON.stringify({
        detail: [
          {
            loc: ["body", "config", "flow", "nodes", 0, "role_message"],
            type: "fact_tool_unavailable",
            msg: "Enable this fact for the node.",
          },
        ],
        diagnostic_id: "safe-diagnostic-123",
        stage: "validation",
        timestamp: "2026-10-03T10:00:00Z",
      }),
      { status: 422, headers: { "Content-Type": "application/json" } },
    );
  try {
    await request("fake-local-token", "/agent-versions/version", {
      method: "PATCH",
      body: "{}",
    });
  } catch (error) {
    failure = error;
  } finally {
    globalThis.fetch = originalFetch;
  }
  assert.ok(failure instanceof ApiError);
  assert.match(failure.message, /config.flow.nodes\[0\].role_message: Enable/);
  assert.equal(failure.diagnostic.diagnostic_id, "safe-diagnostic-123");
  globalThis.__runsAuth = { userId: "editor-user", orgId: "editor-org" };
  const version = {
    id: "version",
    status: "draft",
    version: 1,
    revision: 1,
    note: "",
    config: {
      name: "Ritu",
      flow: { nodes: [] },
      tool_bindings: {},
      pipeline_logs: "inherit",
    },
  };
  const api = async (path, init) => {
    if (init?.method === "PATCH") throw failure;
    if (path === "/agent-versions/version") return version;
    if (path === "/tools") return { tools: [] };
    return {};
  };
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    h(
      QueryClientProvider,
      { client },
      h(
        ApiContext.Provider,
        { value: api },
        h(
          OrganizationAccessContext.Provider,
          { value: { canManage: true } },
          h(
            MemoryRouter,
            {
              initialEntries: [
                "/agents/agent/versions/version?section=logging",
              ],
            },
            h(
              Routes,
              null,
              h(Route, {
                path: "/agents/:agentId/versions/:versionId",
                element: h(AgentEditorPage),
              }),
            ),
          ),
        ),
      ),
    ),
  );
  const note = await screen.findByRole("textbox", { name: "Draft note" });
  fireEvent.change(note, { target: { value: "Keep my draft" } });
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
  await waitFor(() =>
    assert.match(
      screen.getByRole("alert").textContent,
      /config.flow.nodes\[0\].role_message/,
    ),
  );
  assert.ok(screen.getByText("Diagnostic ID: safe-diagnostic-123"));
  assert.ok(screen.getByRole("button", { name: "Copy diagnostic ID" }));
  assert.equal(note.value, "Keep my draft");
});
