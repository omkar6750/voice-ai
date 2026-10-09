import test, { after } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

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
after(() => vite.close());
const { Transcript } = await vite.ssrLoadModule(
  "/src/pages/runs/transcript.tsx",
);
const { Waterfall } = await vite.ssrLoadModule("/src/pages/runs/waterfall.tsx");
const { exchangeVisits } = await vite.ssrLoadModule("/src/pages/runs/model.ts");
const time = (seconds) =>
  `2026-10-09T12:39:${String(seconds).padStart(2, "0")}Z`;
function fixture() {
  return {
    run: { status: "completed" },
    exchanges: [
      {
        id: "e1",
        sequence: 8,
        created_at: time(0),
        origin: "caller",
        status: "completed",
      },
    ],
    messages: [
      {
        id: "m1",
        exchange_id: "e1",
        sequence: 1,
        role: "assistant",
        content: "Next stage reply",
        created_at: time(19),
      },
    ],
    tools: [
      {
        id: "t1",
        exchange_id: "e1",
        binding_key: "classify_lead",
        started_at: time(17),
        ended_at: time(18),
        arguments: {},
        result: {},
        status: "completed",
        receipts: [],
      },
    ],
    flow_visits: [
      {
        id: "v1",
        sequence: 3,
        node_key: "hot_followup",
        span_id: "s1",
        entered_at: time(18),
        triggered_by_tool_id: "t1",
      },
    ],
    spans: [],
    tool_results: [],
    diagnostics: [],
    context_events: [],
    tool_context_deliveries: [],
    classifier_results: [],
    classifier_context_deliveries: [],
    interruptions: [],
  };
}

test("transcript shows the recorded destination between classifier and next reply", () => {
  const timeline = fixture();
  const html = renderToStaticMarkup(
    createElement(Transcript, { timeline, active: false, onSelect() {} }),
  );
  assert.ok(
    html.indexOf("Called classify_lead") < html.indexOf("Entered hot_followup"),
  );
  assert.ok(
    html.indexOf("Entered hot_followup") < html.indexOf("Next stage reply"),
  );
  assert.equal((html.match(/Entered hot_followup/g) ?? []).length, 1);
});

test("historical unlinked visits use recorded timestamps and appear only once", () => {
  const timeline = fixture();
  timeline.flow_visits[0].triggered_by_tool_id = null;
  timeline.exchanges.push({ id: "e2", sequence: 9, created_at: time(30) });
  assert.equal(exchangeVisits(timeline, timeline.exchanges[0]).length, 1);
  assert.equal(exchangeVisits(timeline, timeline.exchanges[1]).length, 0);
  timeline.flow_visits = [];
  assert.deepEqual(exchangeVisits(timeline, timeline.exchanges[0]), []);
});

test("backend requests stay recorded but are collapsed outside the conversation waterfall", () => {
  const timeline = fixture();
  timeline.spans.push({
    id: "api1",
    category: "http_request",
    name: "Backend API request",
    exchange_id: null,
  });
  const html = renderToStaticMarkup(
    createElement(Waterfall, {
      timeline,
      selection: { kind: "run" },
      onSelect() {},
    }),
  );
  assert.ok(html.includes("API request details (1)"));
  assert.ok(!html.includes("Backend API request"));
  assert.equal(timeline.spans.length, 1);
});
