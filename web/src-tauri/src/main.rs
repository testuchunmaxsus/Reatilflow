// RETAIL Desktop — Tauri kirish nuqtasi
// React SPA ni Tauri qobig'iga o'rash

// Windows da konsol oynasini yashirish (release build uchun)
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("Tauri ilovasini ishga tushirishda xato");
}
