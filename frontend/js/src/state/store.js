// Medirover dashboard state store (pure logic — unit tested with node --test).
// The UI renders from this store only; no presentation code mutates it.

const MAX_EVENTS = 200;

export function createStore(initial = {}) {
  const state = {
    connected: false,
    feedMode: "connecting", // connecting | live | polling
    nodes: {}, // node_id -> state dict
    events: [], // newest first
    serverTime: null,
    ...initial,
  };
  const listeners = new Set();

  return {
    state,
    subscribe(fn) {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
    applySnapshot(payload) {
      state.nodes = {};
      for (const node of payload.nodes || []) {
        state.nodes[node.node_id] = { ...node };
      }
      state.events = (payload.events || []).slice(0, MAX_EVENTS);
      state.feedMode = "live";
      emit();
    },
    applyUpdate(nodeId, nodeState) {
      state.nodes[nodeId] = { ...(state.nodes[nodeId] || {}), ...nodeState };
      emit();
    },
    applyEvent(event) {
      state.events.unshift(event);
      state.events = state.events.slice(0, MAX_EVENTS);
      emit();
    },
    setFeedMode(mode) {
      if (state.feedMode !== mode) {
        state.feedMode = mode;
        emit();
      }
    },
    setConnected(v) {
      if (state.connected !== v) {
        state.connected = v;
        emit();
      }
    },
    setServerTime(ts) {
      state.serverTime = ts;
      emit();
    },
    nodeIds() {
      return Object.keys(state.nodes).sort();
    },
  };

  function emit() {
    for (const fn of listeners) fn(state);
  }
}
