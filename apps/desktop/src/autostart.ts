import { enable, disable, isEnabled } from "@tauri-apps/plugin-autostart";

export async function getAutostart(): Promise<boolean> {
  if (!("__TAURI_INTERNALS__" in window)) return false;
  try {
    return await isEnabled();
  } catch {
    return false;
  }
}

export async function setAutostart(enabled: boolean): Promise<void> {
  if (!("__TAURI_INTERNALS__" in window)) return;
  if (enabled) {
    await enable();
  } else {
    await disable();
  }
}
