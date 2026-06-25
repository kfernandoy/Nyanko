mod sidecar;
mod tray;

use tauri::Manager;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|_app, _args, _cwd| {}))
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            Some(vec!["--minimized"]),
        ))
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            sidecar::start(app.handle())?;
            app.manage(tray::DetectionPaused::default());
            tray::setup(app.handle()).map_err(|err| format!("Failed to setup tray: {err}"))?;
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.hide();
            }
            if let tauri::WindowEvent::Destroyed = event {
                sidecar::stop(window.app_handle());
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running Nyanko");
}
