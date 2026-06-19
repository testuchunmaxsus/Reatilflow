/// Ilova konfiguratsiyasi.
///
/// API base URL — sirlar kodga yozilmaydi.
/// Ishlab chiqarishda --dart-define orqali beriladi:
///   flutter run --dart-define=API_BASE_URL=https://api.example.com
///
/// Lokal dev:
///   flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
abstract final class AppConfig {
  /// API serveri manzili.
  /// --dart-define bilan beriladi yoki lokal dev (localhost).
  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000', // Android emulator → lokal host
  );
}
