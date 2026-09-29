// Node status card renderer (pure DOM construction, no business logic).

const CONNECTIVITY_CHIP = {
  ONLINE: ["chip-live", "LIVE"],
  STALE: ["chip-stale", "STALE"],
  OFFLINE: ["chip-offline", "OFFLINE"],
  CONNECTING: ["chip-connecting", "CONNECTING"],
  DISCONNECTED: ["chip-disconnected", "DISCONNECTED"],
};

const SAFETY_CHIP = {
  SAFE: ["chip-safe", "SAFE"],
  READY: ["chip-ready", "READY"],
  ACTIVE: ["chip-active", "ACTIVE"],
  WARNING: ["chip-warning", "WARNING"],
  FAULT: ["chip-fault", "FAULT"],
  EMERGENCY_STOP: ["chip-emergency-stop", "E-STOP"],
  RECOVERY: ["chip-recovery", "RECOVERY"],
};

function chip(classAndLabel, value, title) {
  const [cls, label] = classAndLabel[value] || ["chip-unknown", value || "UNKNOWN"];
  const el = document.createElement("span");
  el.className = `chip ${cls}`;
  el.textContent = label;
  if (title) el.title = title;
  return el;
}

function metric(label, value) {
  const row = document.createElement("div");
  row.className = "row";
  const k = document.createElement("span");
  k.className = "k";
  k.textContent = label;
  const v = document.createElement("span");
  v.className = "val";
  v.textContent = value == null ? "—" : value;
  row.append(k, v);
  return row;
}

function fmtTimeAgo(iso, nowMs) {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "—";
  const s = Math.max(0, Math.round((nowMs - t) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s ago`;
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m ago`;
}

export function renderNodeCard(node, nowMs) {
  const card = document.createElement("article");
  card.className = "card";
  card.dataset.nodeId = node.node_id;

  const header = document.createElement("header");
  const name = document.createElement("div");
  name.className = "name";
  name.textContent = node.name || node.node_id;
  const nid = document.createElement("div");
  nid.className = "nid";
  nid.textContent = `${node.node_id} · ${node.node_type || "?"} · fw ${node.firmware_version || "?"}`;
  header.append(name, nid);
  card.append(header);

  const chips = document.createElement("div");
  chips.className = "chips";
  const st = node.state || {};
  chips.append(
    chip(CONNECTIVITY_CHIP, st.connectivity, "Backend supervisor view (heartbeat-based)"),
    chip(SAFETY_CHIP, st.safety_state, "Node safety state (from heartbeats)"),
  );
  card.append(chips);

  const metrics = document.createElement("div");
  metrics.className = "metrics";
  const battery = st.battery_voltage != null ? `${st.battery_voltage.toFixed(2)} V` : "—";
  metrics.append(
    metric("heartbeat", fmtTimeAgo(st.last_heartbeat_at, nowMs)),
    metric("battery", battery),
    metric("uptime", st.uptime_s != null ? `${Math.round(st.uptime_s)}s` : "—"),
    metric("safety", st.safety_state || "UNKNOWN"),
  );
  card.append(metrics);

  const telemetry = document.createElement("div");
  telemetry.className = "telemetry";
  for (const [sensorId, sample] of Object.entries(st.last_telemetry || {})) {
    const row = document.createElement("div");
    row.className = "row";
    const k = document.createElement("span");
    k.className = "k";
    k.textContent = sensorId;
    const v = document.createElement("span");
    const degraded = sample.quality === "degraded";
    v.className = degraded ? "val degraded" : "val";
    v.textContent = `${fmtValue(sample.value)} ${sample.unit || ""}${degraded ? " (degraded)" : ""}`;
    row.append(k, v);
    telemetry.append(row);
  }
  if (Object.keys(st.last_telemetry || {}).length === 0) {
    telemetry.append(metric("telemetry", "no data yet"));
  }
  card.append(telemetry);
  return card;
}

function fmtValue(value) {
  if (typeof value !== "number") return String(value);
  if (Math.abs(value) >= 100) return value.toFixed(0);
  if (Number.isInteger(value)) return String(value);
  return value.toFixed(2);
}
