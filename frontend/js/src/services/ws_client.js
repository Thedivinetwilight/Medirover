// WebSocket client for /ws/state with deterministic envelope handling and a
// REST polling fallback (honest label: feed mode LIVE vs POLLING).

import { api } from "./api.js";

function wsUrl() {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${location.host}/ws/state`;
}

function frame(messageType, payload, nodeId = "") {
  return JSON.stringify({
    protocol_version: 1,
    message_version: 1,
    message_type: messageType,
    message_id: crypto.randomUUID(),
    sequence: 0,
    timestamp: new Date().toISOString(),
    node_id: nodeId,
    payload,
  });
}

export class StateClient {
  constructor(onFrame, { pollMs = 3000 } = {}) {
    this.onFrame = onFrame;
    this.pollMs = pollMs;
    this.ws = null;
    this.closedByUs = false;
    this.pollTimer = null;
    this.reconnectDelay = 1000;
  }

  start() {
    this._connect();
  }

  stop() {
    this.closedByUs = true;
    this._stopPolling();
    if (this.ws) this.ws.close();
  }

  _connect() {
    if (this.closedByUs) return;
    let ws;
    try {
      ws = new WebSocket(wsUrl());
    } catch {
      this._startPolling();
      return;
    }
    this.ws = ws;
    ws.onopen = () => {
      this.reconnectDelay = 1000;
      this.onFrame({ kind: "connected", live: true });
    };
    ws.onmessage = (msg) => {
      try {
        const frameData = JSON.parse(msg.data);
        this.onFrame({ kind: "frame", frame: frameData, live: true });
      } catch {
        // ignore unparseable frames
      }
    };
    ws.onclose = () => {
      this.onFrame({ kind: "disconnected" });
      this._startPolling();
      if (!this.closedByUs) {
        setTimeout(() => this._connect(), this.reconnectDelay);
        this.reconnectDelay = Math.min(this.reconnectDelay * 2, 15000);
      }
    };
    ws.onerror = () => {
      try { ws.close(); } catch { /* already closed */ }
    };
  }

  _startPolling() {
    if (this.pollTimer) return;
    this.onFrame({ kind: "mode", mode: "polling" });
    const poll = async () => {
      try {
        const nodes = await api.nodes();
        const events = await api.events(50);
        this.onFrame({ kind: "snapshot", payload: { nodes, events } });
      } catch {
        // backend unreachable — keep polling
      }
    };
    poll();
    this.pollTimer = setInterval(poll, this.pollMs);
  }

  _stopPolling() {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
  }
}
