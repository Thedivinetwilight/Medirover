// Event feed renderer.

const SEVERITIES = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"];

export function renderEventItem(event) {
  const li = document.createElement("li");
  li.className = `event sev-${event.severity || "INFO"}`;

  const top = document.createElement("div");
  const t = document.createElement("span");
  t.className = "t";
  t.textContent = fmtTime(event.timestamp);
  const type = document.createElement("span");
  type.className = `type sev-${event.severity || "INFO"}`;
  type.textContent = event.event_type || "EVENT";
  top.append(t, document.createTextNode(" "), type);

  const msg = document.createElement("div");
  msg.className = "msg";
  msg.textContent = event.message || "";
  li.append(top, msg);
  return li;
}

function fmtTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toISOString().replace("T", " ").slice(11, 19) + "Z";
}

export function isSeverity(sev) {
  return SEVERITIES.includes(sev);
}
