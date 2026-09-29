import assert from "node:assert/strict";
import test from "node:test";
import { bindBrowserPeerLifecycle } from "../src/app/browser-peer-lifecycle.ts";

function peer() {
  return {
    connectionState: "new",
    onconnectionstatechange: null,
    ondatachannel: null,
    close() {},
  };
}

function changeState(target, state) {
  target.connectionState = state;
  target.onconnectionstatechange?.();
}

function signalPeerLeft(target) {
  const channel = { onmessage: null };
  target.ondatachannel?.({ channel });
  channel.onmessage?.({
    data: JSON.stringify({ type: "signalling", message: { type: "peerLeft" } }),
  });
}

function channel() {
  return { onmessage: null };
}

test("connects and ends on remote close", () => {
  const connection = peer();
  let current = connection;
  const events = [];
  bindBrowserPeerLifecycle(
    connection,
    () => current,
    () => events.push("connected"),
    () => events.push("ended"),
  );

  assert.deepEqual(events, []);
  changeState(connection, "connected");
  changeState(connection, "closed");

  assert.deepEqual(events, ["connected", "ended"]);
});

test("ends while connecting when the peer closes", () => {
  const connection = peer();
  const events = [];
  bindBrowserPeerLifecycle(
    connection,
    () => connection,
    () => events.push("connected"),
    () => events.push("ended"),
  );

  changeState(connection, "failed");

  assert.deepEqual(events, ["ended"]);
});

test("ends immediately when Pipecat signals that the peer left", () => {
  const connection = peer();
  const events = [];
  bindBrowserPeerLifecycle(
    connection,
    () => connection,
    () => events.push("connected"),
    () => events.push("ended"),
  );

  signalPeerLeft(connection);

  assert.deepEqual(events, ["ended"]);
});

test("ends from the negotiated client control channel", () => {
  const connection = peer();
  const control = channel();
  let endedCount = 0;
  bindBrowserPeerLifecycle(connection, () => connection, () => {}, () => endedCount++, control);

  control.onmessage?.({
    data: JSON.stringify({ type: "signalling", message: { type: "peerLeft" } }),
  });

  assert.equal(endedCount, 1);
});

test("ignores unrelated or malformed data-channel messages", () => {
  const connection = peer();
  let endedCount = 0;
  bindBrowserPeerLifecycle(connection, () => connection, () => {}, () => endedCount++);
  const channel = { onmessage: null };
  connection.ondatachannel?.({ channel });
  channel.onmessage?.({ data: "not-json" });
  channel.onmessage?.({ data: JSON.stringify({ type: "other" }) });

  assert.equal(endedCount, 0);
});

test("latches ended and ignores subsequent state events", () => {
  const connection = peer();
  let endedCount = 0;
  bindBrowserPeerLifecycle(
    connection,
    () => connection,
    () => {},
    () => endedCount++,
  );

  changeState(connection, "disconnected");
  changeState(connection, "closed");

  assert.equal(endedCount, 1);
});

test("ignores events from a stale replaced peer", () => {
  const oldPeer = peer();
  const currentPeer = peer();
  let current = oldPeer;
  const events = [];
  bindBrowserPeerLifecycle(
    oldPeer,
    () => current,
    () => events.push("connected"),
    () => events.push("ended"),
  );
  current = currentPeer;

  changeState(oldPeer, "connected");
  changeState(oldPeer, "closed");

  assert.deepEqual(events, []);
});

test("local cleanup clears peer identity before reentrant close events", () => {
  const connection = peer();
  let current = connection;
  let endedCount = 0;
  bindBrowserPeerLifecycle(
    connection,
    () => current,
    () => {},
    () => endedCount++,
  );

  connection.close = () => {
    current = null;
    changeState(connection, "closed");
  };
  current = null;
  connection.close();

  assert.equal(endedCount, 0);
});

test("invalidates a pending answer after disconnect", () => {
  const connection = peer();
  let current = connection;
  let answerApplied = false;
  const lifecycle = bindBrowserPeerLifecycle(
    connection,
    () => current,
    () => {},
    () => {
      current = null;
    },
  );

  changeState(connection, "closed");
  if (lifecycle.isCurrent()) answerApplied = true;

  assert.equal(answerApplied, false);
});
