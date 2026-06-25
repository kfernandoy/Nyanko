const api = globalThis.browser ?? globalThis.chrome;
const byId = (id) => document.getElementById(id);
const lines = (value) => value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean);

async function load() {
  const config = await api.storage.local.get({ apiUrl: "http://127.0.0.1:8765", label: "Navegador", allowedSites: [], blockedSites: [], token: "" });
  byId("api-url").value = config.apiUrl;
  byId("label").value = config.label;
  byId("allowed").value = config.allowedSites.join("\n");
  byId("blocked").value = config.blockedSites.join("\n");
  byId("status").textContent = config.token ? "Extensión emparejada." : "Pendiente de emparejar.";
}

byId("pair").addEventListener("click", async () => {
  const apiUrl = byId("api-url").value.trim().replace(/\/$/, "");
  const label = byId("label").value.trim() || "Navegador";
  try {
    const response = await fetch(`${apiUrl}/api/extension/pair`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ code: byId("code").value.trim(), label }) });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
    await api.storage.local.set({ apiUrl, label, token: payload.token, tokenExpiresAt: payload.expires_at });
    byId("status").textContent = "Emparejamiento completado.";
    byId("code").value = "";
  } catch (error) { byId("status").textContent = error instanceof Error ? error.message : String(error); }
});

byId("save").addEventListener("click", async () => {
  await api.storage.local.set({ allowedSites: lines(byId("allowed").value), blockedSites: lines(byId("blocked").value) });
  byId("status").textContent = "Preferencias de sitios guardadas.";
});

void load();
