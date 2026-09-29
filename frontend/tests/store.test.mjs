// Pure-logic tests for the dashboard state store (run: node --test).
import test from "node:test";
import assert from "node:assert/strict";
import { createStore } from "../js/src/state/store.js";

test("store starts empty and applies snapshot", () => {
  const store = createStore();
  assert.equal(store.nodeIds().length, 0);
  store.applySnapshot({
    nodes: [{ node_id: "a", connectivity: "ONLINE" }, { node_id: "b", connectivity: "OFFLINE" }],
    events: [{ event_type: "E1" }],
  });
  assert.deepEqual(store.nodeIds(), ["a", "b"]);
  assert.equal(store.state.feedMode, "live");
  assert.equal(store.state.events.length, 1);
});

test("store applies state updates and keeps order", () => {
  const store = createStore();
  store.applySnapshot({ nodes: [{ node_id: "a", connectivity: "ONLINE" }], events: [] });
  store.applyUpdate("a", { connectivity: "STALE", battery_voltage: 12.1 });
  assert.equal(store.state.nodes.a.connectivity, "STALE");
  assert.equal(store.state.nodes.a.battery_voltage, 12.1);
});

test("event feed is bounded to 200 and newest-first", () => {
  const store = createStore();
  for (let i = 0; i < 250; i++) store.applyEvent({ event_type: `E${i}` });
  assert.equal(store.state.events.length, 200);
  assert.equal(store.state.events[0].event_type, "E249");
  assert.equal(store.state.events[199].event_type, "E50");
});

test("listeners are notified on mutation and can unsubscribe", () => {
  const store = createStore();
  let calls = 0;
  const unsub = store.subscribe(() => calls++);
  store.applySnapshot({ nodes: [], events: [] });
  unsub();
  store.applySnapshot({ nodes: [], events: [] });
  assert.equal(calls, 1);
});
