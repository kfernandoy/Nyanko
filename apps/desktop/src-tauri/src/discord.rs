use std::sync::Mutex;

use discord_rich_presence::{
    activity::{Activity, Timestamps},
    DiscordIpc, DiscordIpcClient,
};
use serde::Deserialize;
use tauri::State;

// Rich Presence needs a Discord application Client ID (the "Application ID"). Set it
// here, or override with the NYANKO_DISCORD_CLIENT_ID environment variable. If left as
// the sentinel below, RP is a silent no-op.
const DEFAULT_CLIENT_ID: &str = "1521045260342525962";
const UNCONFIGURED: &str = "REPLACE_WITH_YOUR_DISCORD_CLIENT_ID";

fn client_id() -> String {
    std::env::var("NYANKO_DISCORD_CLIENT_ID").unwrap_or_else(|_| DEFAULT_CLIENT_ID.to_string())
}

#[derive(Default)]
pub struct DiscordState(pub Mutex<Option<DiscordIpcClient>>);

#[derive(Deserialize)]
pub struct DiscordActivity {
    details: String,
    state: String,
    start_timestamp: Option<i64>,
}

fn connected(slot: &mut Option<DiscordIpcClient>) -> Result<&mut DiscordIpcClient, String> {
    if slot.is_none() {
        let id = client_id();
        if id.is_empty() || id == UNCONFIGURED {
            return Err("Discord client id not configured".into());
        }
        let mut client = DiscordIpcClient::new(&id).map_err(|err| err.to_string())?;
        client.connect().map_err(|err| err.to_string())?;
        *slot = Some(client);
    }
    Ok(slot.as_mut().expect("client just set"))
}

#[tauri::command]
pub fn discord_set_activity(state: State<'_, DiscordState>, payload: DiscordActivity) {
    let mut slot = state.0.lock().unwrap_or_else(|p| p.into_inner());
    let client = match connected(&mut slot) {
        Ok(client) => client,
        Err(_) => return, // Discord not running or no client id — silently skip.
    };
    // Only include fields the user opted into; Discord rejects empty details/state.
    let mut activity = Activity::new();
    if !payload.details.is_empty() {
        activity = activity.details(&payload.details);
    }
    if !payload.state.is_empty() {
        activity = activity.state(&payload.state);
    }
    if let Some(start) = payload.start_timestamp {
        activity = activity.timestamps(Timestamps::new().start(start));
    }
    if client.set_activity(activity).is_err() {
        // Discord likely closed; drop the client so we reconnect next time.
        *slot = None;
    }
}

#[tauri::command]
pub fn discord_clear_activity(state: State<'_, DiscordState>) {
    let mut slot = state.0.lock().unwrap_or_else(|p| p.into_inner());
    if let Some(client) = slot.as_mut() {
        let _ = client.clear_activity();
    }
}
