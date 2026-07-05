import { invoke } from "@tauri-apps/api/core";

export type DiscordActivity = {
  details: string;
  state: string;
  start_timestamp?: number;
};

export async function setDiscordActivity(payload: DiscordActivity): Promise<void> {
  if (!("__TAURI_INTERNALS__" in window)) return;
  try {
    await invoke("discord_set_activity", { payload });
  } catch {
    // Discord not running / not configured — ignore.
  }
}

export async function clearDiscordActivity(): Promise<void> {
  if (!("__TAURI_INTERNALS__" in window)) return;
  try {
    await invoke("discord_clear_activity");
  } catch {
    // ignore
  }
}
