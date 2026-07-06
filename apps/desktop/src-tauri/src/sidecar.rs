use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::{AppHandle, Emitter, Manager};
use tauri_plugin_shell::process::CommandChild;
use tauri_plugin_shell::ShellExt;

pub struct SidecarHandle(pub Mutex<Option<CommandChild>>);

pub fn start(app: &AppHandle) -> Result<(), String> {
    // During `tauri dev` we rely on the manually started Python backend so that
    // hot-reload and debugging do not require rebuilding the sidecar on every change.
    if cfg!(debug_assertions) {
        eprintln!("Skipping sidecar in development mode");
        return Ok(());
    }

    let data_dir = app
        .path()
        .app_data_dir()
        .map_err(|err| format!("Failed to resolve app data dir: {err}"))?;
    let data_dir_str = data_dir.to_string_lossy().to_string();
    let _ = std::fs::remove_file(data_dir.join("port"));

    let sidecar = app
        .shell()
        .sidecar("nyanko-api")
        .map_err(|err| format!("Failed to create sidecar command: {err}"))?;

    let (mut rx, child) = sidecar
        .env("NYANKO_DATA_DIR", &data_dir_str)
        .spawn()
        .map_err(|err| format!("Failed to spawn sidecar: {err}"))?;

    app.manage(SidecarHandle(Mutex::new(Some(child))));

    let app_clone = app.clone();
    tauri::async_runtime::spawn(async move {
        while let Some(event) = rx.recv().await {
            if let tauri_plugin_shell::process::CommandEvent::Error(err) = event {
                eprintln!("Sidecar error: {err}");
                let _ = app_clone.emit("sidecar-error", err);
            }
        }
    });

    wait_for_port_file(&data_dir)?;
    Ok(())
}

pub fn stop(app: &AppHandle) {
    if let Some(handle) = app.try_state::<SidecarHandle>() {
        if let Ok(mut child) = handle.0.lock() {
            if let Some(child) = child.take() {
                let _ = child.kill();
            }
        }
    }
}

fn wait_for_port_file(data_dir: &std::path::Path) -> Result<(), String> {
    let port_file = data_dir.join("port");
    let start = Instant::now();
    let timeout = Duration::from_secs(30);
    while start.elapsed() < timeout {
        if port_file.exists() {
            return Ok(());
        }
        std::thread::sleep(Duration::from_millis(100));
    }
    Err("Sidecar did not write its port file in time".to_string())
}
