const api = globalThis.browser ?? globalThis.chrome;

async function settings() {
  return api.storage.local.get({
    apiUrl: "http://127.0.0.1:8765",
    token: "",
    tokenExpiresAt: 0,
    label: "Navegador",
  });
}

async function updateBadge(text, color) {
  await api.action.setBadgeBackgroundColor({ color });
  await api.action.setBadgeText({ text });
}

async function autoPair(config) {
  // Invisible token: the extension mints its own. The backend gates this on the
  // browser-set Origin header, which a web page can't forge — so no manual code.
  const response = await fetch(`${config.apiUrl}/api/extension/auto-pair`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ label: config.label }),
  });
  if (!response.ok) throw new Error(`No se pudo emparejar con Nyanko (HTTP ${response.status})`);
  const next = await response.json();
  await api.storage.local.set({ token: next.token, tokenExpiresAt: next.expires_at });
  return { ...config, token: next.token, tokenExpiresAt: next.expires_at };
}

async function rotateIfNeeded(config) {
  if (!config.token || config.tokenExpiresAt > Date.now() / 1000 + 3 * 86400) return config;
  const response = await fetch(`${config.apiUrl}/api/extension/token/rotate`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${config.token}` },
    body: JSON.stringify({ label: config.label }),
  });
  if (!response.ok) throw new Error("No se pudo rotar el token de Nyanko");
  const next = await response.json();
  await api.storage.local.set({ token: next.token, tokenExpiresAt: next.expires_at });
  return { ...config, token: next.token, tokenExpiresAt: next.expires_at };
}

async function publish(event) {
  let config = await settings();
  try {
    if (!config.token) config = await autoPair(config);
    config = await rotateIfNeeded(config);
    const response = await fetch(`${config.apiUrl}/api/extension/events`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${config.token}` },
      body: JSON.stringify(event),
    });
    if (response.status === 401) {
      // Token revoked or expired: drop it so the next event re-pairs automatically.
      await api.storage.local.set({ token: "", tokenExpiresAt: 0 });
      throw new Error("Token de Nyanko inválido; se reintentará el emparejamiento");
    }
    if (!response.ok) throw new Error(`Nyanko respondió HTTP ${response.status}`);
    await api.storage.local.set({ lastEventAt: Date.now(), lastError: "" });
    await updateBadge(event.paused ? "Ⅱ" : "ON", event.paused ? "#8b829e" : "#5d50cb");
    return { ok: true };
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    await api.storage.local.set({ lastError: detail });
    await updateBadge("!", "#c85362");
    return { ok: false, error: detail };
  }
}

api.runtime.onMessage.addListener((message) => {
  if (message?.type === "nyanko-playback") return publish(message.event);
  if (message?.type === "nyanko-status") return settings();
  return undefined;
});
