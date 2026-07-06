const api = globalThis.browser ?? globalThis.chrome;
const byId = (id) => document.getElementById(id);

// content.js reads storage.local.enabledAdapters directly, so writing it here is all
// that's needed — no backend round-trip. The catalog comes from adapters.js (loaded in
// this page), so adding an adapter there gives it a toggle automatically.
async function renderAdapters() {
  const { enabledAdapters = [] } = await api.storage.local.get({ enabledAdapters: [] });
  const enabled = new Set(enabledAdapters);
  const container = byId("adapters");
  container.replaceChildren();
  for (const { name, label } of globalThis.NyankoSiteAdapters.catalog) {
    const row = document.createElement("label");
    row.className = "adapter";
    const box = document.createElement("input");
    box.type = "checkbox";
    box.checked = enabled.has(name);
    box.addEventListener("change", async () => {
      if (box.checked) enabled.add(name); else enabled.delete(name);
      await api.storage.local.set({ enabledAdapters: [...enabled] });
    });
    const text = document.createElement("span");
    text.textContent = label;
    row.append(box, text);
    container.append(row);
  }
}

async function load() {
  const config = await api.storage.local.get({ apiUrl: "http://127.0.0.1:8765", token: "", lastError: "", lastEventAt: 0 });
  byId("api-url").value = config.apiUrl;
  const parts = [config.token ? "Emparejada automáticamente." : "Se emparejará al detectar reproducción."];
  if (config.lastEventAt) parts.push(`Último evento: ${new Date(config.lastEventAt).toLocaleString("es")}.`);
  if (config.lastError) parts.push(`Último error: ${config.lastError}`);
  byId("status").textContent = parts.join(" ");
  await renderAdapters();
}

byId("save").addEventListener("click", async () => {
  const apiUrl = byId("api-url").value.trim().replace(/\/$/, "");
  // Changing the address invalidates the current token; clear it so it re-pairs.
  await api.storage.local.set({ apiUrl, token: "", tokenExpiresAt: 0 });
  byId("status").textContent = "Dirección guardada. Se volverá a emparejar automáticamente.";
});

void load();
