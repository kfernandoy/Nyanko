use std::path::Path;
use std::sync::Mutex;
use std::time::Duration;

use tauri::menu::{Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::TrayIconBuilder;
use tauri::{AppHandle, Emitter, Manager};

const SHOW_LABEL: &str = "Mostrar";
const HIDE_LABEL: &str = "Ocultar";
const PAUSE_LABEL: &str = "Pausar detección";
const RESUME_LABEL: &str = "Reanudar detección";
const QUIT_LABEL: &str = "Salir";

pub struct DetectionPaused(pub Mutex<bool>);

impl Default for DetectionPaused {
    fn default() -> Self {
        Self(Mutex::new(false))
    }
}

pub fn setup(app: &AppHandle) -> Result<(), Box<dyn std::error::Error>> {
    let menu = build_menu(app)?;

    let mut builder = TrayIconBuilder::new();
    // Sin esto la bandeja aparece sin imagen: usar el ícono de la app.
    if let Some(icon) = app.default_window_icon() {
        builder = builder.icon(icon.clone());
    }
    builder
        .menu(&menu)
        .show_menu_on_left_click(true)
        .on_menu_event(move |app, event| match event.id.as_ref() {
            "show" => show_window(app),
            "hide" => hide_window(app),
            "pause" => toggle_detection(app, true),
            "resume" => toggle_detection(app, false),
            "quit" => {
                crate::sidecar::stop(app);
                app.exit(0);
            }
            _ => {}
        })
        .build(app)?;

    Ok(())
}

fn build_menu(app: &AppHandle) -> Result<Menu<tauri::Wry>, Box<dyn std::error::Error>> {
    let paused = app
        .try_state::<DetectionPaused>()
        .map(|s| *s.0.lock().unwrap_or_else(|p| p.into_inner()))
        .unwrap_or(false);

    let show_item = MenuItem::with_id(app, "show", SHOW_LABEL, true, None::<&str>)?;
    let hide_item = MenuItem::with_id(app, "hide", HIDE_LABEL, true, None::<&str>)?;
    let pause_item = MenuItem::with_id(
        app,
        if paused { "resume" } else { "pause" },
        if paused { RESUME_LABEL } else { PAUSE_LABEL },
        true,
        None::<&str>,
    )?;
    let separator = PredefinedMenuItem::separator(app)?;
    let quit_item = MenuItem::with_id(app, "quit", QUIT_LABEL, true, None::<&str>)?;

    Ok(Menu::with_items(
        app,
        &[&show_item, &hide_item, &pause_item, &separator, &quit_item],
    )?)
}

fn show_window(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.unminimize();
        let _ = window.show();
        let _ = window.set_focus();
    }
}

fn hide_window(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.hide();
    }
}

fn toggle_detection(app: &AppHandle, paused: bool) {
    if let Err(err) = set_backend_detection_paused(app, paused) {
        eprintln!("Failed to toggle detection: {err}");
        return;
    }
    if let Some(state) = app.try_state::<DetectionPaused>() {
        if let Ok(mut guard) = state.0.lock() {
            *guard = paused;
        }
    }
    let _ = app.emit("detection-paused", paused);
}

fn set_backend_detection_paused(app: &AppHandle, paused: bool) -> Result<(), String> {
    let data_dir = app
        .path()
        .app_data_dir()
        .map_err(|err| format!("Failed to resolve app data dir: {err}"))?;
    let api_url = resolve_api_url(&data_dir);
    let path = if paused { "pause" } else { "resume" };
    ureq::post(&format!("{api_url}/api/detection/{path}"))
        .timeout(Duration::from_secs(5))
        .call()
        .map_err(|err| format!("HTTP error: {err}"))?;
    Ok(())
}

fn resolve_api_url(data_dir: &Path) -> String {
    let port_file = data_dir.join("port");
    if let Ok(content) = std::fs::read_to_string(&port_file) {
        if let Ok(port) = content.trim().parse::<u16>() {
            return format!("http://127.0.0.1:{port}");
        }
    }
    "http://127.0.0.1:8765".to_string()
}

