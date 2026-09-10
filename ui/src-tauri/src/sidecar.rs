//! Sidecar process lifecycle.
//!
//! The Python sidecar (Presence Studio) is spawned per app launch, prints
//! `PRESENCE_SIDECAR_READY token=… port=…` on stdout, and binds 127.0.0.1.
//! The token is parsed here, held in process memory, and handed to the
//! webview only through the `sidecar_connection` command. It is never
//! logged, persisted, or exposed elsewhere.

use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};

use serde::Serialize;
use tauri::{AppHandle, Emitter, Manager};

#[derive(Clone, Serialize)]
pub struct SidecarConnInfo {
    pub port: u16,
    pub token: String,
}

#[derive(Default)]
pub struct SidecarManager {
    child: Option<Child>,
    conn: Option<SidecarConnInfo>,
}

impl SidecarManager {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn connection(&self) -> Option<SidecarConnInfo> {
        self.conn.clone()
    }

    pub fn start(&mut self, app: &AppHandle) -> Result<(), String> {
        self.kill();
        self.conn = None;
        let cmd = resolve_sidecar_command(app)?;
        let mut child = Command::new(&cmd[0])
            .args(&cmd[1..])
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .map_err(|e| format!("failed to spawn sidecar {:?}: {e}", cmd[0]))?;

        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| "sidecar stdout unavailable".to_string())?;

        let conn = Arc::new(Mutex::new(None::<SidecarConnInfo>));
        let conn_writer = Arc::clone(&conn);
        let app_reader = app.clone();

        // Reader thread: first the handshake line, then discard output.
        std::thread::spawn(move || {
            let reader = BufReader::new(stdout);
            for line in reader.lines() {
                let Ok(line) = line else { break };
                if let Some(info) = parse_ready_line(&line) {
                    if let Ok(mut slot) = conn_writer.lock() {
                        *slot = Some(info.clone());
                    }
                    let _ = app_reader.emit("sidecar://ready", info.port);
                    // Keep draining so the child never blocks on a full pipe.
                }
            }
            let _ = app_reader.emit("sidecar://exit", ());
        });

        // Wait briefly for the handshake so early IPC has a chance to work.
        let deadline = std::time::Instant::now() + std::time::Duration::from_secs(10);
        loop {
            if let Ok(slot) = conn.lock() {
                if let Some(info) = slot.as_ref() {
                    self.conn = Some(info.clone());
                    break;
                }
            }
            if std::time::Instant::now() > deadline {
                break; // frontend will surface offline + restart
            }
            std::thread::sleep(std::time::Duration::from_millis(25));
        }

        self.child = Some(child);
        Ok(())
    }

    pub fn restart(&mut self, app: &AppHandle) -> Result<(), String> {
        self.start(app)
    }

    pub fn kill(&mut self) {
        if let Some(mut child) = self.child.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

impl Drop for SidecarManager {
    fn drop(&mut self) {
        self.kill();
    }
}

/// Parse `PRESENCE_SIDECAR_READY token=<t> port=<p>`.
fn parse_ready_line(line: &str) -> Option<SidecarConnInfo> {
    let line = line.trim();
    if !line.starts_with("PRESENCE_SIDECAR_READY") {
        return None;
    }
    let mut token: Option<String> = None;
    let mut port: Option<u16> = None;
    for part in line.split_whitespace().skip(1) {
        if let Some(v) = part.strip_prefix("token=") {
            token = Some(v.to_string());
        } else if let Some(v) = part.strip_prefix("port=") {
            port = v.parse().ok();
        }
    }
    match (token, port) {
        (Some(token), Some(port)) => Some(SidecarConnInfo { port, token }),
        _ => None,
    }
}

/// Resolution order:
/// 1. VOICEGENAI_SIDECAR_CMD (explicit override, split on whitespace)
/// 2. bundled resource `sidecar/presence-sidecar` (packaged app)
/// 3. dev fallback: repo `.venv/bin/presence-sidecar`
fn resolve_sidecar_command(app: &AppHandle) -> Result<Vec<String>, String> {
    if let Ok(cmd) = std::env::var("VOICEGENAI_SIDECAR_CMD") {
        let parts: Vec<String> = cmd.split_whitespace().map(String::from).collect();
        if !parts.is_empty() {
            return Ok(parts);
        }
    }

    if let Ok(dir) = app.path().resource_dir() {
        let bin = dir
            .join("sidecar")
            .join(if cfg!(windows) {
                "presence-sidecar.exe"
            } else {
                "presence-sidecar"
            });
        if bin.exists() {
            return Ok(vec![bin.to_string_lossy().to_string()]);
        }
    }

    // Dev: <repo>/ui/src-tauri → <repo>/.venv/bin/presence-sidecar
    let manifest = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let dev_bin = manifest
        .join("../../.venv/bin")
        .join(if cfg!(windows) {
            "presence-sidecar.exe"
        } else {
            "presence-sidecar"
        });
    if dev_bin.exists() {
        return Ok(vec![dev_bin.to_string_lossy().to_string()]);
    }

    Err(
        "voice engine not found (set VOICEGENAI_SIDECAR_CMD, bundle the sidecar, or create the repo .venv)"
            .to_string(),
    )
}
