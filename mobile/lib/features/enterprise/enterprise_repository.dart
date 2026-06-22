import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../../data/remote/api_client.dart';
import 'enterprise_model.dart';

/// Enterprise repository — /enterprise/me ni chaqiradi, lokal kesh.
///
/// Lokal kesh: SharedPreferences (oddiy JSON, sirli emas).
/// Offline holat: oxirgi ma'lum enabled_modules ishlatiladi.
class EnterpriseRepository {
  EnterpriseRepository({
    required ApiClient apiClient,
    required SharedPreferences prefs,
  })  : _apiClient = apiClient,
        _prefs = prefs;

  final ApiClient _apiClient;
  final SharedPreferences _prefs;

  static const String _cacheKey = 'enterprise_info_cache';

  /// Serverdan yuklash va kesh yangilash.
  /// Xato bo'lsa — keshni qaytaradi (offline).
  /// Kesh ham yo'q bo'lsa — barcha modul yoqilgan fallback.
  Future<EnterpriseInfo> fetchAndCache() async {
    try {
      final info = await _apiClient.getEnterpriseInfo();
      await _saveCache(info);
      return info;
    } on Exception {
      return getCached() ?? enterpriseAllModules;
    }
  }

  /// Lokal keshdan o'qish (sync, UI freeze yo'q).
  EnterpriseInfo? getCached() {
    final raw = _prefs.getString(_cacheKey);
    if (raw == null) return null;
    try {
      final json = jsonDecode(raw) as Map<String, dynamic>;
      return EnterpriseInfo.fromJson(json);
    } on Exception {
      return null;
    }
  }

  /// Keshni tozalash (logout'da).
  Future<void> clearCache() async {
    await _prefs.remove(_cacheKey);
  }

  Future<void> _saveCache(EnterpriseInfo info) async {
    await _prefs.setString(_cacheKey, jsonEncode(info.toJson()));
  }
}
