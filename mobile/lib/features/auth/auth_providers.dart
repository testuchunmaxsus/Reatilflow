import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/config/app_config.dart';
import '../../data/remote/api_client.dart';
import '../../data/remote/auth_interceptor.dart';
import '../../data/remote/models/auth_models.dart';
import '../../data/remote/token_storage.dart';
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
  AuthNotifier(this._repository) : super(const AuthStateLoading()) {
    _init();
  }

  final AuthRepository _repository;

  Future<void> _init() async {
    final user = await _repository.tryAutoLogin();
    if (user != null) {
      state = AuthStateAuthenticated(user: user);
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
    } on Exception catch (e) {
      state = AuthStateError(message: e.toString());
    }
  }

  Future<void> logout() async {
    await _repository.logout();
    state = const AuthStateUnauthenticated();
  }

  void handleForcedLogout() {
    // Token interceptor tomonidan chaqiriladi (token eskirgan)
    unawaited(_repository.logout());
    state = const AuthStateUnauthenticated();
  }

  MeResponse? get currentUser {
    final s = state;
    if (s is AuthStateAuthenticated) return s.user;
    return null;
  }
}

/// unawaited helper (dart:async import shart emas, dart core da bor)
void unawaited(Future<void> future) => future.ignore();

final authNotifierProvider =
    StateNotifierProvider<AuthNotifier, AuthState>((ref) {
  final repository = ref.watch(authRepositoryProvider);
  return AuthNotifier(repository);
});
