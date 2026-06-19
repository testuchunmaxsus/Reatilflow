import 'package:dio/dio.dart';

import 'auth_interceptor.dart';
import 'models/auth_models.dart';
import 'models/sync_models.dart';

/// REST API klient (Dio).
///
/// AuthInterceptor: Bearer token, 401 → /auth/refresh → retry.
/// UI bu klassni to'g'ridan-to'g'ri ishlatmaydi — SyncService va
/// AuthRepository orqali murojaat qiladi.
class ApiClient {
  ApiClient({
    required String baseUrl,
    required AuthInterceptor authInterceptor,
  }) {
    _dio = Dio(
      BaseOptions(
        baseUrl: baseUrl,
        connectTimeout: const Duration(seconds: 15),
        receiveTimeout: const Duration(seconds: 30),
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json',
        },
      ),
    );

    _dio.interceptors.add(authInterceptor);
    _dio.interceptors.add(LogInterceptor());
  }

  late final Dio _dio;

  Dio get dio => _dio;

  // ---- Auth ----

  Future<TokenPair> login(LoginRequest request) async {
    final response = await _dio.post<Map<String, dynamic>>(
      '/auth/login',
      data: request.toJson(),
    );
    return TokenPair.fromJson(response.data!);
  }

  Future<TokenPair> refreshToken(RefreshRequest request) async {
    final response = await _dio.post<Map<String, dynamic>>(
      '/auth/refresh',
      data: request.toJson(),
    );
    return TokenPair.fromJson(response.data!);
  }

  Future<void> logout(LogoutRequest request) async {
    await _dio.post<void>(
      '/auth/logout',
      data: request.toJson(),
    );
  }

  Future<MeResponse> getMe() async {
    final response = await _dio.get<Map<String, dynamic>>('/auth/me');
    return MeResponse.fromJson(response.data!);
  }

  // ---- Sync Push ----

  Future<SyncPushResponse> syncPush(SyncPushRequest request) async {
    final response = await _dio.post<Map<String, dynamic>>(
      '/sync/push',
      data: request.toJson(),
    );
    return SyncPushResponse.fromJson(response.data!);
  }

  // ---- Sync Pull ----

  Future<SyncPullResponse> syncPull({
    required int since,
    int limit = 50,
  }) async {
    final response = await _dio.get<Map<String, dynamic>>(
      '/sync/pull',
      queryParameters: {'since': since, 'limit': limit},
    );
    return SyncPullResponse.fromJson(response.data!);
  }

  // ---- Delivery ----

  /// Yetkazish holat o'zgartirish.
  /// DELIVERY.md: PATCH /delivery/{id}/status
  Future<Map<String, dynamic>> updateDeliveryStatus({
    required String deliveryId,
    required String status,
    required int version,
    String? gpsLat,
    String? gpsLng,
    String? failureReason,
  }) async {
    final body = <String, dynamic>{
      'status': status,
      'version': version,
      if (gpsLat != null) 'gps_lat': gpsLat,
      if (gpsLng != null) 'gps_lng': gpsLng,
      if (failureReason != null) 'failure_reason': failureReason,
    };
    final response = await _dio.patch<Map<String, dynamic>>(
      '/delivery/$deliveryId/status',
      data: body,
    );
    return response.data!;
  }

  /// Dalil rasmi yuklash (multipart).
  /// DELIVERY.md: POST /delivery/{id}/proof-photo
  ///
  /// NOTE(T20-camera): [formData] ni DeliveryRepository.uploadProofPhoto()
  /// ichida FormData.fromMap({'file': MultipartFile.fromFile(path)}) bilan
  /// tayyorlang. AuthInterceptor (401 → refresh) ishlaydigan Dio instance
  /// orqali yuboriladi.
  Future<Map<String, dynamic>> uploadProofPhoto({
    required String deliveryId,
    required FormData formData,
  }) async {
    final response = await _dio.post<Map<String, dynamic>>(
      '/delivery/$deliveryId/proof-photo',
      data: formData,
      options: Options(contentType: 'multipart/form-data'),
    );
    return response.data!;
  }

  /// GPS ingest — DELIVERY.md + GPS.md
  /// POST /gps/ingest — delivery_id bilan
  Future<Map<String, dynamic>> gpsIngest(
      Map<String, dynamic> payload) async {
    final response = await _dio.post<Map<String, dynamic>>(
      '/gps/ingest',
      data: payload,
    );
    return response.data!;
  }
}

