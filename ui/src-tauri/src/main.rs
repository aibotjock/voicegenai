#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

//! VoiceGenAI desktop shell.
//!
//! The webview UI talks to the local FastAPI sidecar; this process owns the
//! sidecar lifecycle (spawn → handshake → restart → kill on exit) and is the
//! only place the per-launch bearer token exists outside the webview.

mod sidecar;

use sidecar::{SidecarConnInfo, SidecarManager};
use std::sync::Mutex;
use tauri::{Manager, RunEvent};

struct AppState {
    sidecar: Mutex<SidecarManager>,
}

#[tauri::command]
fn sidecar_connection(state: tauri::State<'_, AppState>) -> Result<SidecarConnInfo, String> {
    state
        .sidecar
        .lock()
        .map_err(|_| "state unavailable".to_string())?
        .connection()
        .ok_or_else(|| "sidecar not ready".to_string())
}

#[tauri::command]
fn restart_sidecar(app: tauri::AppHandle, state: tauri::State<'_, AppState>) -> Result<(), String> {
    state
        .sidecar
        .lock()
        .map_err(|_| "state unavailable".to_string())?
        .restart(&app)
}

fn main() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_http::init())
        .plugin(tauri_plugin_fs::init())
        .manage(AppState {
            sidecar: Mutex::new(SidecarManager::new()),
        })
        .invoke_handler(tauri::generate_handler![sidecar_connection, restart_sidecar])
        .setup(|app| {
            // Spawn off the main thread so the window appears immediately;
            // the UI shows "Starting Voice Engine…" until the handshake lands.
            let handle = app.handle().clone();
            std::thread::spawn(move || {
                let state = handle.state::<AppState>();
                if let Ok(mut mgr) = state.sidecar.lock() {
                    if let Err(e) = mgr.start(&handle) {
                        eprintln!("sidecar failed to start: {e}");
                        let _ = handle.emit("sidecar://start-failed", e);
                    }
                }
            });
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building VoiceGenAI");

    app.run(|app_handle, event| {
        if matches!(event, RunEvent::ExitRequested { .. } | RunEvent::Exit) {
            let state = app_handle.state::<AppState>();
            if let Ok(mut mgr) = state.sidecar.lock() {
                mgr.kill();
            }
        }
    });
}
