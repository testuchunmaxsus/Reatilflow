import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/config/app_config.dart';
import '../../data/local/database_provider.dart';
import '../../data/remote/api_client.dart';
import '../../data/remote/auth_interceptor.dart';
import '../../data/remote/models/auth_models.dart';
import '../../data/remote/token_storage.dart';
import '../enterprise/enterprise_providers.dart';
import 'auth_repository.dart';

/// Token saqlash provider
final tokenStorageProvider = Provider<TokenStorage>(
  (ref) => SecureTokenStorage(),
);

/// API klient provider (auth interceptor ichida)
/// Sikliy bog'liqlikdan qochish uchun AuthInterceptor
/// onLogout callback ni kechiktirib (closure) oladi.
final apiClientProvider = Provider<ApiClient>((ref) {
  final tokenStorage = ref.watch(tokenStorageProvider);

  // onLogout — auth notifier ni sikliy import qilmasdan chaqirish uchun
  // ProviderRef.invalidate bilan yechiladi: authNotifier ni reset qilamiz
  final authInterceptor = AuthInterceptor(
    tokenStorage: tokenStorage,
    baseUrl: AppConfig.apiBaseUrl,
    // Interceptor auth notifier ga to'g'ridan-to'g'ri murojaat qila olmaydi
    // (sikliy bog'liqlik). Token o'chirilsa, keyingi getMe() xatosida
    // notifier unauthenticated ga tushadi.
    onLogout: tokenStorage.clearTokens,
  );

  return ApiClient(
    baseUrl: AppConfig.apiBaseUrl,
    authInterceptor: authInterceptor,
  );
});

/// Auth repository provider
final authRepositoryProvider = Provider<AuthRepository>((ref) {
  final apiClient = ref.watch(apiClientProvider);
  final tokenStorage = ref.watch(tokenStorageProvider);
  return AuthRepository(
    apiClient: apiClient,
    tokenStorage: tokenStorage,
  );
});

/// Auth holat notifier
class AuthNotifier extends StateNotifier<AuthState> {
  AuthNotifier(this._repository, this._ref) : super(const AuthStateLoading()) {
    _init();
  }

  final AuthRepository _repository;
  final Ref _ref;

  Future<void> _init() async {
    final user = await _repository.tryAutoLogin();
    if (user != null) {
      state = AuthStateAuthenticated(user: user);
      // Korxona ma'lumotlarini yuklash (background)
      unawaited(
        _ref.read(enterpriseNotifierProvider.notifier).refresh(),
      );
    } else {
      state = const AuthStateUnauthenticated();
    }
  }

  Future<void> login({
    required String phone,
    required String password,
  }) async {
    state = const AuthStateLoading();
    try {
      final user = await _repository.login(phone: phone, password: password);
      state = AuthStateAuthenticated(user: user);
      // Login muvaffaqiyatli — enterprise modullarni yuklash
      unawaited(
        _ref.read(enterpriseNotifierProvider.notifier).refresh(),
      );
    } on DioException catch (e) {
      // Suspended korxona → 403 + message_key: enterprise.suspended
      final isSuspended = _isSuspendedError(e);
      if (isSuspended) {
        state = const AuthStateError(
          message:
              "Korxona faollashtirilmagan yoki to'xtatilgan. "
              'Iltimos, administrator bilan bog\'laning.',
        );
      } else {
        state = AuthStateError(message: _parseErrorMessage(e));
      }
    } on Exception catch (e) {
      state = AuthStateError(message: e.toString());
    }
  }

  Future<void> logout() async {
    await _repository.logout();
    // Enterprise keshni tozalash
    await _ref.read(enterpriseNotifierProvider.notifier).clear();
    // Lokal Drift bazasini tozalash — qurilma almashinuvida
    // yangi agent o'z do'konlarini to'liq sync qilishi uchun
    await _ref.read(databaseProvider).clearAllData();
    state = const AuthStateUnauthenticated();
  }

  void handleForcedLogout() {
    // Token interceptor tomonidan chaqiriladi (token eskirgan)
    unawaited(_repository.logout());
    unawaited(_ref.read(enterpriseNotifierProvider.notifier).clear());
    state = const AuthStateUnauthenticated();
  }

  MeResponse? get currentUser {
    final s = state;
    if (s is AuthStateAuthenticated) return s.user;
    return null;
  }

  /// Backend envelope: { "detail": { "message_key": "enterprise.suspended" } }
  /// yoki { "message_key": "enterprise.suspended" }
  bool _isSuspendedError(DioException e) {
    if (e.response?.statusCode != 403) return false;
    final data = e.response?.data;
    if (data == null) return false;
    final key = _extractMessageKey(data);
    return key == 'enterprise.suspended';
  }

  String? _extractMessageKey(dynamic data) {
    if (data is Map<String, dynamic>) {
      final direct = data['message_key'];
      if (direct is String) return direct;
      final detail = data['detail'];
      if (detail is Map<String, dynamic>) {
        return detail['message_key'] as String?;
      }
    }
    return null;
  }

  String _parseErrorMessage(DioException e) {
    final data = e.response?.data;
    if (data is Map<String, dynamic>) {
      final msg = data['detail'] ?? data['message'] ?? data['error'];
      if (msg is String) return msg;
    }
    return e.message ?? e.toString();
  }
}

/// unawaited helper (dart:async import shart emas, dart core da bor)
void unawaited(Future<void> future) => future.ignore();

final authNotifierProvider =
    StateNotifierProvider<AuthNotifier, AuthState>((ref) {
  final repository = ref.watch(authRepositoryProvider);
  return AuthNotifier(repository, ref);
});
