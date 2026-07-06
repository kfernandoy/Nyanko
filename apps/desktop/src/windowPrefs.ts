import { invoke } from "@tauri-apps/api/core";

export type WindowPrefs = {
  close_to_tray: boolean;
  minimize_to_tray: boolean;
  start_minimized: boolean;
};

const DEFAULTS: WindowPrefs = {
  close_to_tray: false,
  minimize_to_tray: false,
  start_minimized: false,
};

export async function getWindowPrefs(): Promise<WindowPrefs> {
  if (!("__TAURI_INTERNALS__" in window)) return DEFAULTS;
  try {
    return await invoke<WindowPrefs>("get_window_prefs");
  } catch {
    return DEFAULTS;
  }
}

export async function setWindowPrefs(prefs: WindowPrefs): Promise<void> {
  if (!("__TAURI_INTERNALS__" in window)) return;
  await invoke("set_window_prefs", { prefs });
}
