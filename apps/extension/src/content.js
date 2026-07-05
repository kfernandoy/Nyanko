const api = globalThis.browser ?? globalThis.chrome;
const SEND_INTERVAL_MS = 5000;
let lastSentAt = 0;
let lastSignature = "";
let overlay;
let scheduledPublish;
// Video state reported by a subframe (embedded player) up to the top frame, which
// owns the page identity (series/episode from its URL). null until one arrives.
let subframeVideo = null;
let lastSubframePaused = null;

// Tracking is opt-in per adapter: nothing is scanned until the user enables an
// adapter in the app. Empty list = track nowhere. "generic" enables scanning any
// unmatched site via JSON-LD/metadata.
async function adapterEnabled(name) {
  const config = await api.storage.local.get({ enabledAdapters: [] });
  const enabled = (config.enabledAdapters || []).map((value) => String(value).toLowerCase());
  return enabled.includes(name);
}

function activeVideo() {
  return [...document.querySelectorAll("video")]
    .filter((video) => video.duration > 0 && video.readyState >= 2)
    .sort((left, right) => right.clientWidth * right.clientHeight - left.clientWidth * left.clientHeight)[0];
}

function videoSource(video) {
  return video.currentSrc || video.src || "";
}

// Build a synthetic <video> stand-in from a subframe report, or null if it's stale
// (older than 8s) or has no usable duration.
function syntheticFromReport(report, now) {
  if (!report || now - report.at >= 8000 || !report.duration) return null;
  return { currentTime: report.position ?? 0, duration: report.duration, paused: report.paused, ended: false };
}

// The video to publish: the top frame's own, or — when the player is in a cross-origin
// iframe — a synthetic stand-in built from the subframe's reported timing.
function effectiveVideo() {
  return activeVideo() || syntheticFromReport(subframeVideo, Date.now());
}

// Subframe side: forward this frame's playing video up to the top frame. The subframe
// can't know the real series (its URL is the embed host), so it never publishes itself.
function reportToTop() {
  const video = activeVideo();
  if (!video) return;
  try {
    window.top.postMessage({
      __nyanko: "video",
      position: Number.isFinite(video.currentTime) ? video.currentTime : null,
      duration: Number.isFinite(video.duration) ? video.duration : null,
      paused: video.paused || video.ended,
    }, "*");
  } catch { /* a cross-origin top can reject the post; nothing to do */ }
}

function episodeSignature(adapterName, detected, href, videoSrc) {
  // A stable per-site identifier plus a real episode number is language- and
  // URL-independent, so key on that alone: the same episode keeps one signature
  // across localized paths (/es-es/…), reordered query strings or changing blob
  // srcs — no duplicate events, and progress stays under one cache key.
  if (detected.siteIdentifier && detected.episode != null) {
    return [adapterName, detected.siteIdentifier, detected.season ?? "", detected.episode].join("|");
  }
  // No stable anchor (generic page with no parsed episode): keep the full context
  // so genuinely distinct videos don't collapse onto one signature.
  return [
    adapterName,
    detected.siteIdentifier || "",
    detected.animeTitle || "",
    detected.season ?? "",
    detected.episode ?? "",
    detected.rawTitle || "",
    href,
    videoSrc || "",
  ].join("|");
}

function progressKey(signature) {
  return `nyanko-progress:${signature}`;
}

async function persistProgress(signature, video) {
  if (!signature || !Number.isFinite(video.currentTime) || !Number.isFinite(video.duration)) return;
  await api.storage.local.set({
    [progressKey(signature)]: {
      position_seconds: video.currentTime,
      duration_seconds: video.duration,
      updated_at: Date.now(),
    },
  });
}

function showObserved(show) {
  if (!show) {
    overlay?.remove();
    overlay = undefined;
    return;
  }
  if (overlay) return;
  overlay = document.createElement("div");
  overlay.textContent = "Nyanko observa este reproductor";
  Object.assign(overlay.style, {
    position: "fixed", right: "12px", bottom: "12px", zIndex: "2147483647",
    padding: "7px 10px", borderRadius: "7px", color: "#fff",
    background: "rgba(33,29,61,.9)", font: "12px system-ui,sans-serif",
  });
  document.documentElement.append(overlay);
}

async function publish(force = false) {
  const adapter = globalThis.NyankoSiteAdapters.select();
  if (!(await adapterEnabled(adapter.name))) return showObserved(false);
  const video = effectiveVideo();
  if (!video) return showObserved(false);
  const now = Date.now();
  const detected = adapter.detect(video);
  const signature = episodeSignature(adapter.name, detected, location.href, videoSource(video));
  force ||= signature !== lastSignature;
  if (!force && now - lastSentAt < SEND_INTERVAL_MS) return;
  lastSentAt = now;
  lastSignature = signature;
  await persistProgress(signature, video);
  showObserved(!video.paused && !video.ended);
  await api.runtime.sendMessage({
    type: "nyanko-playback",
    event: {
      raw_title: detected.rawTitle, page_url: location.href,
      position_seconds: Number.isFinite(video.currentTime) ? video.currentTime : null,
      duration_seconds: Number.isFinite(video.duration) ? video.duration : null,
      paused: video.paused || video.ended,
      anime_title: detected.animeTitle,
      season: detected.season,
      episode: detected.episode,
      content_kind: detected.contentKind,
      site_adapter: adapter.name,
      site_identifier: detected.siteIdentifier || null,
      search_hints: detected.searchHints || [],
      next_episode_url: detected.nextEpisodeUrl || null,
    },
  });
}

function schedulePublish(force = false) {
  clearTimeout(scheduledPublish);
  scheduledPublish = setTimeout(() => void publish(force), 300);
}

function installLocationWatcher() {
  for (const method of ["pushState", "replaceState"]) {
    const original = history[method];
    history[method] = function patchedHistoryMethod(...args) {
      const result = original.apply(this, args);
      window.dispatchEvent(new Event("nyanko-locationchange"));
      return result;
    };
  }
  window.addEventListener("popstate", () => schedulePublish(true));
  window.addEventListener("hashchange", () => schedulePublish(true));
  window.addEventListener("nyanko-locationchange", () => schedulePublish(true));
}

function installWatchers() {
  document.addEventListener("play", () => void publish(true), true);
  document.addEventListener("pause", () => void publish(true), true);
  document.addEventListener("ended", () => void publish(true), true);
  document.addEventListener("loadedmetadata", () => schedulePublish(true), true);
  document.addEventListener("durationchange", () => schedulePublish(true), true);
  document.addEventListener("fullscreenchange", () => schedulePublish(true), true);
  window.addEventListener("message", (event) => {
    const data = event.data;
    if (!data || data.__nyanko !== "video" || !data.duration) return;
    // Cualquier iframe embebido (anuncios, widgets) puede postear al top frame y el
    // origen del reproductor real no se puede fijar entre sitios; al menos se exige
    // que posición/duración sean coherentes antes de aceptar el reporte.
    const duration = Number(data.duration);
    const position = data.position == null ? 0 : Number(data.position);
    if (!Number.isFinite(duration) || duration <= 0 || duration > 43200) return;
    if (!Number.isFinite(position) || position < 0 || position > duration) return;
    const paused = Boolean(data.paused);
    const pausedChanged = paused !== lastSubframePaused;
    lastSubframePaused = paused;
    subframeVideo = { position, duration, paused, at: Date.now() };
    schedulePublish(pausedChanged);
  });
  new MutationObserver(() => schedulePublish()).observe(document.documentElement, {
    childList: true,
    subtree: true,
    characterData: true,
  });
  installLocationWatcher();
  // Heartbeat. setInterval alone is throttled to ~1/min in background tabs, so the
  // backend's 15s window expires whenever the user focuses the app and the detection
  // flickers. timeupdate keeps firing at full rate while media actually plays (even
  // backgrounded); publish() self-throttles to SEND_INTERVAL_MS, so this stays cheap.
  document.addEventListener("timeupdate", () => void publish(), true);
  window.setInterval(() => void publish(), 3000);
}

function installSubframeReporter() {
  document.addEventListener("play", reportToTop, true);
  document.addEventListener("pause", reportToTop, true);
  document.addEventListener("ended", reportToTop, true);
  // timeupdate survives background-tab throttling (see installWatchers); the top frame
  // debounces and throttles, so reporting at the media's native rate is harmless.
  document.addEventListener("timeupdate", reportToTop, true);
  window.setInterval(reportToTop, 2000);
}

globalThis.NyankoPlaybackContent = { episodeSignature, progressKey, syntheticFromReport };

if (typeof document !== "undefined" && api?.runtime) {
  if (window.top === window) installWatchers();
  else installSubframeReporter();
}
