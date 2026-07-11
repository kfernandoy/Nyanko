import { native } from "./native";

// Delgado wrapper sobre la frontera nativa: mantiene las firmas que usan App.tsx y
// DetectorSettingsView. native.getAutostart/setAutostart son stubs de Fase 4 (NATIVE-06).
export const getAutostart = (): Promise<boolean> => native.getAutostart();
export const setAutostart = (enabled: boolean): Promise<void> => native.setAutostart(enabled);
