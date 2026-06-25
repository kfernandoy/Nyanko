const api = globalThis.browser ?? globalThis.chrome;
const SEND_INTERVAL_MS = 5000;
let lastSentAt = 0;
let lastSignature = "";
let overlay;
let scheduledPublish;

function domainMatches(hostname, patterns) {
  return patterns.some((pattern) => hostname === pattern || hostname.endsWith(`.${pattern}`));
}

async function siteEnabled() {
  const config = await api.storage.local.get({ allowedSites: [], blockedSites: [] });
  const host = location.hostname.toLowerCase();
  const allowed = config.allowedSites.map((value) => value.toLowerCase()).filter(Boolean);
  const blocked = config.blockedSites.map((value) => value.toLowerCase()).filter(Boolean);
  if (domainMatches(host, blocked)) return false;
  return allowed.length === 0 || domainMatches(host, allowed);
}

function activeVideo() {
  return [...document.querySelectorAll("video")]
    .filter((video) => video.duration > 0 && video.readyState >= 2)
    .sort((left, right) => right.clientWidth * right.clientHeight - left.clientWidth * left.clientHeight)[0];
}

function videoSource(video) {
  return video.currentSrc || video.src || "";
}

function episodeSignature(adapterName, detected, href, videoSrc) {
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
  if (!(await siteEnabled())) return showObserved(false);
  const video = activeVideo();
  if (!video) return showObserved(false);
  const now = Date.now();
  const adapter = globalThis.NyankoSiteAdapters.select();
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
  new MutationObserver(() => schedulePublish()).observe(document.documentElement, {
    childList: true,
    subtree: true,
    characterData: true,
  });
  installLocationWatcher();
  window.setInterval(() => void publish(), 3000);
}

globalThis.NyankoPlaybackContent = { episodeSignature, progressKey };

if (typeof document !== "undefined" && api?.runtime) installWatchers();
