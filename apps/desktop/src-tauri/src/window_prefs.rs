use std::fs;
use std::path::PathBuf;
use std::sync::Mutex;

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Manager, State};

#[derive(Clone, Copy, Serialize, Deserialize)]
pub struct WindowPrefs {
    pub close_to_tray: bool,
    pub minimize_to_tray: bool,
    pub start_minimized: bool,
}

impl Default for WindowPrefs {
    fn default() -> Self {
        Self {
            close_to_tray: false,
            minimize_to_tray: false,
            start_minimized: false,
        }
    }
}

pub struct WindowPrefsState(pub Mutex<WindowPrefs>);

fn prefs_path(app: &AppHandle) -> Option<PathBuf> {
    app.path()
        .app_data_dir()
        .ok()
        .map(|dir| dir.join("window_prefs.json"))
}

pub fn load(app: &AppHandle) -> WindowPrefs {
    prefs_path(app)
        .and_then(|path| fs::read_to_string(path).ok())
        .and_then(|raw| serde_json::from_str(&raw).ok())
        .unwrap_or_default()
}

fn persist(app: &AppHandle, prefs: &WindowPrefs) {
    if let Some(path) = prefs_path(app) {
        if let Some(parent) = path.parent() {
            let _ = fs::create_dir_all(parent);
        }
        if let Ok(raw) = serde_json::to_string_pretty(prefs) {
            let _ = fs::write(path, raw);
        }
    }
}

pub fn current(app: &AppHandle) -> WindowPrefs {
    app.try_state::<WindowPrefsState>()
        .map(|state| *state.0.lock().unwrap_or_else(|p| p.into_inner()))
        .unwrap_or_default()
}

#[tauri::command]
pub fn get_window_prefs(state: State<'_, WindowPrefsState>) -> WindowPrefs {
    *state.0.lock().unwrap_or_else(|p| p.into_inner())
}

#[tauri::command]
pub fn set_window_prefs(app: AppHandle, state: State<'_, WindowPrefsState>, prefs: WindowPrefs) {
    {
        let mut guard = state.0.lock().unwrap_or_else(|p| p.into_inner());
        *guard = prefs;
    }
    persist(&app, &prefs);
}
