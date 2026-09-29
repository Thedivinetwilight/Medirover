// Medirover dashboard bootstrap: store -> services -> render.
// All state comes from the backend (live WS with REST polling fallback).
// No fake metrics are ever generated here (master directive §16).

import { api } from "./services/api.js";
import { StateClient } from "./services/ws_client.js";
import { createStore } from "./state/store.js";
import { renderNodeCard } from "./components/status_card.js";
import { renderEventItem } from "./components/event_feed.js";

const store = createStore();

const nodesEl = document.getElementById("nodes");
const nodesEmpty = document.getElementById("nodes-empty");
const eventsEl = document.getElementById("events");
const feedModeEl = document.getElementById("feed-mode");
const nodeCountEl = document.getElementById("node-count");
const versionEl = document.getElementById("api-version");
const serverTimeEl = document.getElementById("server-time");

function renderNodes() {
  const s = store.state;
  const ids = store.nodeIds();
  nodesEl.querySelectorAll(".card").forEach((c) => {
    if (!ids.includes(c.dataset.nodeId)) c.remove();
  });
  for (const id of ids) {
    let card = nodesEl.querySelector(`.card[data-node-id="${CSS.escape(id)}"]`);
    if (!card) {
      card = renderNodeCard(s.nodes[id], Date.now());
      nodesEl.append(card);
    } else {
      // update in place (cheap re-render of text content)
      const fresh = renderNodeCard(s.nodes[id], Date.now());
      card.replaceWith(fresh);
    }
  }
  nodesEmpty.style.display = ids.length === 0 ? "" : "none";
  nodeCountEl.textContent = `${ids.length} node${ids.length === 1 ? "" : "s"}`;
}

function renderEvents() {
  const s = store.state;
  eventsEl.replaceChildren(...s.events.slice(0, 200).map(renderEventItem));
}

function renderFeedMode() {
  const mode = store.state.feedMode;
  feedModeEl.textContent =
    mode === "live" ? "LIVE FEED (WS)" : mode === "polling" ? "POLLING (REST)" : "CONNECTING…";
  feedModeEl.className = `feed-mode ${mode === "live" ? "live" : mode === "polling" ? "polling" : ""}`;
}

store.subscribe(() => {
  renderNodes();
  renderEvents();
  renderFeedMode();
});

const client = new StateClient((msg) => {
  if (msg.kind === "connected") {
    store.setConnected(true);
    store.setFeedMode("live");
  } else if (msg.kind === "disconnected") {
    store.setConnected(false);
  } else if (msg.kind === "mode" && msg.mode === "polling") {
    store.setFeedMode("polling");
  } else if (msg.kind === "snapshot" && msg.payload) {
    store.applySnapshot(msg.payload);
  } else if (msg.kind === "frame" && msg.frame) {
    const f = msg.frame;
    if (f.message_type === "state_snapshot") store.applySnapshot(f.payload);
    else if (f.message_type === "state_update") store.applyUpdate(f.node_id, f.payload);
    else if (f.message_type === "event") store.applyEvent(f.payload);
  }
});
client.start();

async function refreshHealth() {
  try {
    const health = await api.health();
    versionEl.textContent = `v${health.version}`;
    serverTimeEl.textContent = health.server_time.replace("T", " ").slice(0, 19) + "Z";
  } catch {
    versionEl.textContent = "v? (backend unreachable)";
  }
}
refreshHealth();
setInterval(refreshHealth, 10000);

// Initial REST snapshot in case the WS snapshot arrives late
api.events(50).then((events) => {
  if (store.state.events.length === 0) {
    store.state.events = events;
    renderEvents();
  }
}).catch(() => { /* backend not up yet; WS/retry will deliver */ });
