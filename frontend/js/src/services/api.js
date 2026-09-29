// REST client for the Medirover API (v1). Relative URLs only.

async function getJSON(path) {
  const resp = await fetch(path, { headers: { Accept: "application/json" } });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    const err = new Error(`HTTP ${resp.status} ${path}`);
    err.apiError = body.error || null;
    throw err;
  }
  return resp.json();
}

export const api = {
  health: () => getJSON("/api/v1/health"),
  nodes: () => getJSON("/api/v1/nodes"),
  node: (id) => getJSON(`/api/v1/nodes/${encodeURIComponent(id)}`),
  telemetry: (id, limit = 50) => getJSON(`/api/v1/nodes/${encodeURIComponent(id)}/telemetry?limit=${limit}`),
  events: (limit = 100) => getJSON(`/api/v1/events?limit=${limit}`),
};
