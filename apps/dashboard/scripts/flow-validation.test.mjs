import test from "node:test";
import assert from "node:assert/strict";
import { createServer } from "vite";

test("initial response validation agrees with backend task role requirements", async () => {
  const server = await createServer({ configFile: false, optimizeDeps: { noDiscovery: true, include: [] }, server: { middlewareMode: true } });
  try {
    const { openingTaskError } = await server.ssrLoadModule("/src/pages/agents/flow-validation.ts");
    const config = (messages, respond = true) => ({ flow: { initial_node: "greeting", nodes: [{ id: "greeting", respond_immediately: respond, task_messages: messages }] } });
    for (const messages of [[], [{role: "system", content: "Greet"}], [{role: "developer", content: "Greet"}], [{role: "user", content: "  "}]]) {
      assert.match(openingTaskError(config(messages)), /nonempty user task message/);
    }
    assert.equal(openingTaskError(config([{role: "user", content: "Introduce yourself, then wait."}])), null);
    assert.equal(openingTaskError(config([], false)), null);
  } finally {
    await server.close();
  }
});
