// Sin esto el binario es una app de consola y Windows abre una ventana cmd junto a la app.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    nyanko_desktop_lib::run();
}
