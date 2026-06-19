import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Token saqlash abstraktsiyasi — Keychain (iOS) / Keystore (Android).
///
/// Sirlar (access_token, refresh_token) hech qachon SharedPreferences yoki
/// oddiy fayl saqlashga tushirilmaydi.
abstract class TokenStorage {
  Future<String?> getAccessToken();
  Future<String?> getRefreshToken();
  Future<void> saveTokens({
    required String accessToken,
    required String refreshToken,
  });
  Future<void> clearTokens();
  Future<bool> hasTokens();
}

/// Ishlab chiqarish implementatsiyasi — FlutterSecureStorage
class SecureTokenStorage implements TokenStorage {
  SecureTokenStorage()
      : _storage = const FlutterSecureStorage(
          aOptions: AndroidOptions(
            encryptedSharedPreferences: true,
          ),
          iOptions: IOSOptions(
            accessibility: KeychainAccessibility.first_unlock_this_device,
          ),
        );

  final FlutterSecureStorage _storage;

  static const String _accessKey = 'retail_access_token';
  static const String _refreshKey = 'retail_refresh_token';

  @override
  Future<String?> getAccessToken() => _storage.read(key: _accessKey);

  @override
  Future<String?> getRefreshToken() => _storage.read(key: _refreshKey);

  @override
  Future<void> saveTokens({
    required String accessToken,
    required String refreshToken,
  }) async {
    await Future.wait([
      _storage.write(key: _accessKey, value: accessToken),
      _storage.write(key: _refreshKey, value: refreshToken),
    ]);
  }

  @override
  Future<void> clearTokens() async {
    await Future.wait([
      _storage.delete(key: _accessKey),
      _storage.delete(key: _refreshKey),
    ]);
  }

  @override
  Future<bool> hasTokens() async {
    final access = await _storage.read(key: _accessKey);
    return access != null && access.isNotEmpty;
  }
}

/// Test uchun — xotiradagi implementatsiya
class InMemoryTokenStorage implements TokenStorage {
  String? _accessToken;
  String? _refreshToken;

  @override
  Future<String?> getAccessToken() async => _accessToken;

  @override
  Future<String?> getRefreshToken() async => _refreshToken;

  @override
  Future<void> saveTokens({
    required String accessToken,
    required String refreshToken,
  }) async {
    _accessToken = accessToken;
    _refreshToken = refreshToken;
  }

  @override
  Future<void> clearTokens() async {
    _accessToken = null;
    _refreshToken = null;
  }

  @override
  Future<bool> hasTokens() async =>
      _accessToken != null && _accessToken!.isNotEmpty;
}
