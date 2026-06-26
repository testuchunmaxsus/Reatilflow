import '../../data/remote/api_client.dart';
import '../../data/remote/models/auth_models.dart';
import '../../data/remote/token_storage.dart';

/// Auth holatlari
sealed class AuthState {
  const AuthState();
}

class AuthStateUnauthenticated extends AuthState {
  const AuthStateUnauthenticated();
}

class AuthStateAuthenticated extends AuthState {
  const AuthStateAuthenticated({required this.user});
  final MeResponse user;
}

class AuthStateLoading extends AuthState {
  const AuthStateLoading();
}

class AuthStateError extends AuthState {
  const AuthStateError({required this.message});
  final String message;
}

/// Auth repository — login, refresh, logout, token saqlash.
///
/// flutter_secure_storage (TokenStorage) + Dio (ApiClient).
class AuthRepository {
  AuthRepository({
    required ApiClient apiClient,
    required TokenStorage tokenStorage,
  })  : _apiClient = apiClient,
        _tokenStorage = tokenStorage;

  final ApiClient _apiClient;
  final TokenStorage _tokenStorage;

  MeResponse? _currentUser;
  MeResponse? get currentUser => _currentUser;

  /// Login — telefon + parol → token saqlash
  Future<MeResponse> login({
    required String phone,
    required String password,
  }) async {
    final tokens = await _apiClient.login(
      LoginRequest(phone: phone, password: password),
    );

    await _tokenStorage.saveTokens(
      accessToken: tokens.accessToken,
      refreshToken: tokens.refreshToken,
    );

    final user = await _apiClient.getMe();
    _currentUser = user;
    return user;
  }

  /// Token bor-yo'qligini tekshirish (app ochilganda)
  Future<MeResponse?> tryAutoLogin() async {
    final hasTokens = await _tokenStorage.hasTokens();
    if (!hasTokens) return null;

    try {
      final user = await _apiClient.getMe();
      _currentUser = user;
      return user;
    } on Exception {
      // Token eskirgan yoki xato — null qaytaramiz (login sahifasiga)
      return null;
    }
  }

  /// Logout — tokenlarni o'chirish
  Future<void> logout() async {
    final refreshToken = await _tokenStorage.getRefreshToken();
    if (refreshToken != null) {
      try {
        await _apiClient.logout(LogoutRequest(refreshToken: refreshToken));
      } on Exception {
        // Server xatosi bo'lsa ham lokal tokenlarni o'chir
      }
    }
    await _tokenStorage.clearTokens();
    _currentUser = null;
  }

  /// PATCH /auth/me — O'z profilini yangilash (full_name, locale).
  ///
  /// Faqat o'zining profilini yangilaydi — alohida RBAC ruxsati kerak emas.
  /// [fullName] va [locale] null bo'lsa o'zgartirilmaydi.
  Future<MeResponse> patchMe({
    String? fullName,
    String? locale,
  }) async {
    final body = <String, dynamic>{
      if (fullName != null) 'full_name': fullName,
      if (locale != null) 'locale': locale,
    };
    final user = await _apiClient.patchMe(body);
    _currentUser = user;
    return user;
  }

  /// Foydalanuvchi roli
  String? get userRole => _currentUser?.role;

  /// Foydalanuvchi ID
  String? get userId => _currentUser?.id;
}
