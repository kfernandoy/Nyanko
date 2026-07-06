mod discord;
mod sidecar;
mod tray;
mod window_prefs;

use tauri::Manager;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            // Relanzar la app (o abrirla estando en la bandeja) debe traer al frente la
            // instancia viva; sin esto el segundo proceso salía sin mostrar nada y parecía
            // colgada.
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.unminimize();
                let _ = window.set_focus();
            }
        }))
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            Some(vec!["--minimized"]),
        ))
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_process::init())
        .manage(discord::DiscordState::default())
        .invoke_handler(tauri::generate_handler![
            window_prefs::get_window_prefs,
            window_prefs::set_window_prefs,
            discord::discord_set_activity,
            discord::discord_clear_activity
        ])
        .setup(|app| {
            let prefs = window_prefs::load(app.handle());
            app.manage(window_prefs::WindowPrefsState(std::sync::Mutex::new(prefs)));

            // La ventana arranca oculta (visible: false en la config); la mostramos salvo
            // que el usuario pidiera iniciar minimizada (ajuste o flag de autostart).
            // Se muestra antes de arrancar el sidecar para que sea visible aunque el
            // backend tarde o falle al iniciar.
            let start_minimized =
                prefs.start_minimized || std::env::args().any(|arg| arg == "--minimized");
            if !start_minimized {
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.show();
                    let _ = window.set_focus();
                }
            }

            sidecar::start(app.handle())?;
            app.manage(tray::DetectionPaused::default());
            tray::setup(app.handle()).map_err(|err| format!("Failed to setup tray: {err}"))?;
            Ok(())
        })
        .on_window_event(|window, event| match event {
            tauri::WindowEvent::CloseRequested { api, .. } => {
                if window_prefs::current(window.app_handle()).close_to_tray {
                    api.prevent_close();
                    let _ = window.hide();
                } else {
                    crate::sidecar::stop(window.app_handle());
                    window.app_handle().exit(0);
                }
            }
            tauri::WindowEvent::Resized(_) => {
                if window_prefs::current(window.app_handle()).minimize_to_tray
                    && window.is_minimized().unwrap_or(false)
                {
                    let _ = window.hide();
                }
            }
            tauri::WindowEvent::Destroyed => {
                sidecar::stop(window.app_handle());
            }
            _ => {}
        })
        .run(tauri::generate_context!())
        .expect("error while running Nyanko");
}
