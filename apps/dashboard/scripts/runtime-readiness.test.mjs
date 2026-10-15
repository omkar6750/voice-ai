import test from "node:test";
import assert from "node:assert/strict";
import { waitForRuntime } from "../src/app/runtime-readiness.ts";

const fast = { deadlineMs: 100, pollMs: 1 };
test("cold/busy runtime is polled with GETs until ready", async () => {
  const states = ["starting", "busy", "ready"];
  const calls = [];
  await waitForRuntime(async (path, init) => {
    calls.push({ path, init });
    return { state: states.shift() };
  }, new AbortController().signal, fast);
  assert.equal(calls.length, 3);
  assert.ok(calls.every(c => c.path === "/runtime-readiness" && !c.init.method));
});
test("cancellation prevents subsequent preparation", async () => {
  const controller = new AbortController();
  let prepared = false;
  const run = waitForRuntime(async () => {
    controller.abort();
    return {state: "ready"};
  }, controller.signal, fast).then(() => { prepared = true; });
  await assert.rejects(run, {name: "AbortError"});
  assert.equal(prepared, false);
});
test("authentication failure is not retried", async () => {
  let calls = 0;
  await assert.rejects(waitForRuntime(async () => {
    calls++;
    return {state: "unavailable", code: "runtime_authentication_failed"};
  }, new AbortController().signal, fast), /runtime_authentication_failed/);
  assert.equal(calls, 1);
});
test("startup has a bounded deadline", async () => {
  await assert.rejects(waitForRuntime(async () => ({state: "starting"}),
    new AbortController().signal, {deadlineMs: 15, pollMs: 2}), /two minutes/);
});
