const api = globalThis.browser ?? globalThis.chrome;
const config = await api.storage.local.get({ token: "", lastEventAt: 0, lastError: "" });
document.getElementById("state").textContent = config.lastError || (config.token ? (config.lastEventAt ? `Último evento: ${new Date(config.lastEventAt).toLocaleTimeString()}` : "Emparejada; esperando reproducción.") : "No emparejada.");
document.getElementById("options").addEventListener("click", () => api.runtime.openOptionsPage());
