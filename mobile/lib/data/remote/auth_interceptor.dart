import 'package:dio/dio.dart';

import '../remote/token_storage.dart';

/// Dio interceptor: har so'rovga Bearer token qo'shadi.
/// 401 javob kelganda refresh token bilan yangi access oladi,
/// asl so'rovni qayta yuboradi.
///
/// Loop oldini olish: agar /auth/refresh o'zi 401 qaytarsa — logout.
class AuthInterceptor extends Interceptor {
  AuthInterceptor({
    required TokenStorage tokenStorage,
    required String baseUrl,
    required void Function() onLogout,
  })  : _tokenStorage = tokenStorage,
        _baseUrl = baseUrl,
        _onLogout = onLogout;

  final TokenStorage _tokenStorage;
  final String _baseUrl;
  final void Function() _onLogout;

  // Refresh paytida parallel so'rovlarni to'xtatib turish uchun flag
  bool _isRefreshing = false;
  final List<_PendingRequest> _pendingRequests = [];

  @override
  Future<void> onRequest(
    RequestOptions options,
    RequestInterceptorHandler handler,
  ) async {
    // /auth/login va /auth/refresh ochiq endpointlar — token kerak emas
    if (_isAuthEndpoint(options.path)) {
      handler.next(options);
      return;
    }

    final token = await _tokenStorage.getAccessToken();
    if (token != null) {
      options.headers['Authorization'] = 'Bearer $token';
    }
    handler.next(options);
  }

  @override
  Future<void> onError(
    DioException err,
    ErrorInterceptorHandler handler,
  ) async {
    if (err.response?.statusCode != 401) {
      handler.next(err);
      return;
    }

    // /auth/refresh 401 = logout
    if (_isAuthEndpoint(err.requestOptions.path)) {
      _onLogout();
      handler.next(err);
      return;
    }

    if (_isRefreshing) {
      // Refresh jarayonida — navbatga qo'shish
      _pendingRequests.add(_PendingRequest(err.requestOptions, handler));
      return;
    }

    _isRefreshing = true;
    try {
      final newTokens = await _performRefresh();
      if (newTokens == null) {
        _onLogout();
        _failPending(err);
        handler.next(err);
        return;
      }

      // Navbatdagilarni qayta yubor
      await _retryPending(newTokens.accessToken);

      // Asl so'rovni qayta yubor
      final retryResponse = await _retry(
        err.requestOptions,
        newTokens.accessToken,
      );
      handler.resolve(retryResponse);
    } catch (_) {
      _onLogout();
      _failPending(err);
      handler.next(err);
    } finally {
      _isRefreshing = false;
    }
  }

  bool _isAuthEndpoint(String path) =>
      path.contains('/auth/login') ||
      path.contains('/auth/refresh') ||
      path.contains('/auth/logout');

  Future<_TokenResult?> _performRefresh() async {
    final refreshToken = await _tokenStorage.getRefreshToken();
    if (refreshToken == null) return null;

    try {
      final dio = Dio(
        BaseOptions(
          baseUrl: _baseUrl,
          connectTimeout: const Duration(seconds: 10),
          receiveTimeout: const Duration(seconds: 10),
        ),
      );

      final response = await dio.post<Map<String, dynamic>>(
        '/auth/refresh',
        data: {'refresh_token': refreshToken},
      );

      final data = response.data!;
      final accessToken = data['access_token'] as String;
      final newRefresh = data['refresh_token'] as String;

      await _tokenStorage.saveTokens(
        accessToken: accessToken,
        refreshToken: newRefresh,
      );

      return _TokenResult(accessToken: accessToken);
    } catch (_) {
      return null;
    }
  }

  Future<Response<dynamic>> _retry(
    RequestOptions options,
    String accessToken,
  ) async {
    final dio = Dio(BaseOptions(baseUrl: _baseUrl));
    return dio.request<dynamic>(
      options.path,
      data: options.data,
      queryParameters: options.queryParameters,
      options: Options(
        method: options.method,
        headers: {
          ...options.headers,
          'Authorization': 'Bearer $accessToken',
        },
      ),
    );
  }

  Future<void> _retryPending(String accessToken) async {
    for (final pending in _pendingRequests) {
      try {
        final response = await _retry(pending.options, accessToken);
        pending.handler.resolve(response);
      } catch (e) {
        pending.handler.next(
          DioException(requestOptions: pending.options, error: e),
        );
      }
    }
    _pendingRequests.clear();
  }

  void _failPending(DioException err) {
    for (final pending in _pendingRequests) {
      pending.handler.next(err);
    }
    _pendingRequests.clear();
  }
}

class _PendingRequest {
  _PendingRequest(this.options, this.handler);
  final RequestOptions options;
  final ErrorInterceptorHandler handler;
}

class _TokenResult {
  _TokenResult({required this.accessToken});
  final String accessToken;
}
