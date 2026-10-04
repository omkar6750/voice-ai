import test, { after } from "node:test";
import assert from "node:assert/strict";
import { readFile, writeFile, mkdir, unlink } from "node:fs/promises";
import ts from "typescript";

await mkdir(new URL("../.cache/", import.meta.url), { recursive: true });
const source = await readFile(
  new URL("../src/lib/query-client.ts", import.meta.url),
  "utf8",
);
const { outputText: code } = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.ESNext,
    target: ts.ScriptTarget.ES2022,
  },
});
const compiled = new URL("../.cache/query-client-test.mjs", import.meta.url);
await writeFile(compiled, code);
after(async () => { await unlink(compiled); });
const {
  queryClient,
  isSafeQuery,
  restoreQueryCache,
  persistQueryCache,
  clearQueryCache,
} = await import(compiled.href);

class Storage extends Map {
  get length() {
    return this.size;
  }
  key(index) {
    return [...this.keys()][index] ?? null;
  }
  getItem(key) {
    return this.get(key) ?? null;
  }
  setItem(key, value) {
    this.set(key, value);
  }
  removeItem(key) {
    this.delete(key);
  }
}
globalThis.sessionStorage = new Storage();
const callbacks = new Map();
let counter = 0;
globalThis.window = {
  requestIdleCallback: (fn) => {
    callbacks.set(++counter, fn);
    return counter;
  },
  cancelIdleCallback: (id) => callbacks.delete(id),
};
const key = ["resource", "org", "no-support-session", "/tools", "user"];

test("sensitive and support data never qualify for persistence", () => {
  for (const path of [
    "/contacts",
    "/credentials",
    "/agent-versions/a",
    "/runs/a/timeline",
    "/runs/a",
    "/secrets",
  ])
    assert.equal(
      isSafeQuery({
        queryKey: ["resource", "org", "no-support-session", path, "user"],
      }),
      false,
    );
  assert.equal(
    isSafeQuery({
      queryKey: ["resource", "org", "support-token", "/tools", "user"],
    }),
    false,
  );
  assert.equal(isSafeQuery({ queryKey: key }), true);
});

test("cache writes debounce until idle; fetch events do not write; cleanup cancels writes", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const stop = persistQueryCache("user");
  queryClient.setQueryData(key, { tools: [{ id: "a", name: "one" }] });
  queryClient.setQueryData(key, { tools: [{ id: "a", name: "two" }] });
  assert.equal(sessionStorage.size, 0);
  t.mock.timers.tick(1000);
  assert.equal(callbacks.size, 1);
  [...callbacks.values()][0]();
  callbacks.clear();
  assert.equal(sessionStorage.size, 1);
  queryClient.setQueryData(key, { tools: [] });
  stop();
  t.mock.timers.tick(1000);
  assert.equal(callbacks.size, 0);
  queryClient.clear();
  sessionStorage.clear();
});

test("oversized entries are omitted; expired cache and legacy cache are removed", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const stop = persistQueryCache("user");
  queryClient.setQueryData(key, { tools: ["x".repeat(2 * 1024 * 1024)] });
  t.mock.timers.tick(1000);
  [...callbacks.values()][0]();
  callbacks.clear();
  const cacheKey = "dashboard-query-cache-v2:user";
  assert.ok(Buffer.byteLength(sessionStorage.getItem(cacheKey)) <= 1024 * 1024);
  assert.equal(
    JSON.parse(sessionStorage.getItem(cacheKey)).state.queries.length,
    0,
  );
  stop();
  queryClient.clear();
  const envelope = JSON.parse(sessionStorage.getItem(cacheKey));
  envelope.savedAt = Date.now() - 31 * 60_000;
  sessionStorage.setItem(cacheKey, JSON.stringify(envelope));
  sessionStorage.setItem("dashboard-query-cache-v1:user", "legacy");
  restoreQueryCache("user");
  assert.equal(sessionStorage.size, 0);
});

test("another user's queries are excluded from this user's cache", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const stop = persistQueryCache("user");
  queryClient.setQueryData(key, { tools: [] });
  queryClient.setQueryData([...key.slice(0, 4), "another-user"], {
    tools: [{ id: "private" }],
  });
  t.mock.timers.tick(1000);
  [...callbacks.values()][0]();
  callbacks.clear();
  const saved = JSON.parse(
    sessionStorage.getItem("dashboard-query-cache-v2:user"),
  );
  assert.equal(saved.state.queries.length, 1);
  assert.deepEqual(saved.state.queries[0].queryKey, key);
  stop();
  queryClient.clear();
  sessionStorage.clear();
});

test("sign-out clears all authenticated caches", () => {
  sessionStorage.setItem("dashboard-query-cache-v2:user", "data");
  queryClient.setQueryData(key, { tools: [] });
  clearQueryCache();
  assert.equal(sessionStorage.size, 0);
  assert.equal(queryClient.getQueryCache().getAll().length, 0);
});
