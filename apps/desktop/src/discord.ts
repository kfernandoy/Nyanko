import { native } from "./native";

// El tipo vive ahora en native.ts; se re-exporta para no tocar los call sites de App.tsx.
export type { DiscordActivity } from "./native";
import type { DiscordActivity } from "./native";

// Rich Presence (NATIVE-05): no-op silencioso si Discord no corre — ver electron/main/discord.ts.
export const setDiscordActivity = (payload: DiscordActivity): Promise<void> =>
  native.setDiscordActivity(payload);
export const clearDiscordActivity = (): Promise<void> => native.clearDiscordActivity();
