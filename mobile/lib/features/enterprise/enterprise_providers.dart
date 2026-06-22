import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../auth/auth_providers.dart';
import 'enterprise_model.dart';
import 'enterprise_repository.dart';

/// SharedPreferences provider (async — bir marta yuklanadi).
final sharedPreferencesProvider = Provider<SharedPreferences>((ref) {
  throw UnimplementedError(
    'sharedPreferencesProvider ni main()da override qiling:\n'
    '  final prefs = await SharedPreferences.getInstance();\n'
    '  ProviderScope(overrides: [sharedPreferencesProvider.overrideWithValue(prefs)])',
  );
});

/// Enterprise repository provider.
final enterpriseRepositoryProvider = Provider<EnterpriseRepository>((ref) {
  final api = ref.watch(apiClientProvider);
  final prefs = ref.watch(sharedPreferencesProvider);
  return EnterpriseRepository(apiClient: api, prefs: prefs);
});

/// Enterprise holat notifier.
///
/// Login'dan keyin [refresh] chaqiriladi (AuthNotifier tomonidan yoki
/// app ochilganda tryAutoLogin muvaffaqiyatli bo'lgandan so'ng).
/// Offline bo'lsa keshdan foydalanadi.
class EnterpriseNotifier extends StateNotifier<EnterpriseInfo> {
  EnterpriseNotifier(this._repository) : super(enterpriseAllModules) {
    _loadFromCache();
  }

  final EnterpriseRepository _repository;

  /// Keshdan sinxron o'qish (tezkor start).
  void _loadFromCache() {
    final cached = _repository.getCached();
    if (cached != null) {
      state = cached;
    }
  }

  /// Serverdan yangilash (login'dan keyin yoki refresh).
  Future<void> refresh() async {
    final info = await _repository.fetchAndCache();
    state = info;
  }

  /// Logout'da tozalash.
  Future<void> clear() async {
    await _repository.clearCache();
    state = enterpriseAllModules;
  }

  /// Modul yoqilganmi? (UI shortcut)
  bool hasModule(String key) => state.hasModule(key);
}

final enterpriseNotifierProvider =
    StateNotifierProvider<EnterpriseNotifier, EnterpriseInfo>((ref) {
  final repository = ref.watch(enterpriseRepositoryProvider);
  return EnterpriseNotifier(repository);
});

/// Faqat enabled_modules ro'yxatini kuzatuvchi convenience provider.
final enabledModulesProvider = Provider<List<String>>((ref) {
  return ref.watch(enterpriseNotifierProvider).enabledModules;
});

/// Bitta modul holatini kuzatuvchi family provider.
/// Ishlatish: ref.watch(moduleEnabledProvider('delivery'))
final moduleEnabledProvider = Provider.family<bool, String>((ref, moduleKey) {
  return ref.watch(enterpriseNotifierProvider).hasModule(moduleKey);
});
