import 'package:dio/dio.dart';

import '../../features/enterprise/enterprise_model.dart';
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

  // ---- Enterprise ----

  /// GET /enterprise/me — korxona ma'lumotlari (enabled_modules).
  Future<EnterpriseInfo> getEnterpriseInfo() async {
    final response =
        await _dio.get<Map<String, dynamic>>('/enterprise/me');
    return EnterpriseInfo.fromJson(response.data!);
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

  // ---- POS ----

  /// GET /marketplace/inventory — do'kon inventari (expiry bayroqlari bilan).
  Future<List<dynamic>> getInventory() async {
    final response = await _dio.get<dynamic>('/marketplace/inventory');
    final data = response.data;
    if (data is List) return data;
    if (data is Map<String, dynamic>) {
      return data['items'] as List? ?? [];
    }
    return [];
  }

  /// POST /pos/sales — sotuv yaratish (product_id + qty FAQAT, narx yubormaydi).
  Future<Map<String, dynamic>> createPosSale(
      Map<String, dynamic> body) async {
    final response = await _dio.post<Map<String, dynamic>>(
      '/pos/sales',
      data: body,
    );
    return response.data!;
  }

  /// GET /pos/summary?date=YYYY-MM-DD — kunlik sotuv hisoboti.
  Future<Map<String, dynamic>> getPosSummary({required String date}) async {
    final response = await _dio.get<Map<String, dynamic>>(
      '/pos/summary',
      queryParameters: {'date': date},
    );
    return response.data!;
  }

  // ---- Marketplace ----

  /// GET /marketplace/banners?limit=N — reklama bannerlari.
  Future<dynamic> getMarketplaceBanners({int limit = 5}) async {
    final response = await _dio.get<dynamic>(
      '/marketplace/banners',
      queryParameters: {'limit': limit},
    );
    return response.data;
  }

  /// GET /marketplace/promos?limit=N — qaynoq aksiyalar (supplier nomi bilan).
  Future<dynamic> getMarketplacePromos({int limit = 20}) async {
    final response = await _dio.get<dynamic>(
      '/marketplace/promos',
      queryParameters: {'limit': limit},
    );
    return response.data;
  }

  /// GET /marketplace/products — mahsulotlar ro'yxati.
  Future<dynamic> browseProducts({
    String? search,
    String? supplierEnterpriseId,
  }) async {
    final params = <String, dynamic>{
      if (search != null && search.isNotEmpty) 'search': search,
      if (supplierEnterpriseId != null && supplierEnterpriseId.isNotEmpty)
        'supplier_enterprise_id': supplierEnterpriseId,
    };
    final response = await _dio.get<dynamic>(
      '/marketplace/products',
      queryParameters: params.isEmpty ? null : params,
    );
    return response.data;
  }

  /// POST /marketplace/orders — buyurtma yaratish (product_id + qty FAQAT).
  Future<Map<String, dynamic>> createMarketplaceOrder(
      Map<String, dynamic> body) async {
    final response = await _dio.post<Map<String, dynamic>>(
      '/marketplace/orders',
      data: body,
    );
    return response.data!;
  }

  /// GET /marketplace/orders/outgoing — chiquvchi buyurtmalar.
  Future<dynamic> getOutgoingOrders() async {
    final response =
        await _dio.get<dynamic>('/marketplace/orders/outgoing');
    return response.data;
  }

  /// GET /marketplace/orders/{id} — bitta buyurtma.
  Future<Map<String, dynamic>> getMarketplaceOrder(String orderId) async {
    final response = await _dio.get<Map<String, dynamic>>(
      '/marketplace/orders/$orderId',
    );
    return response.data!;
  }

  /// PATCH /marketplace/orders/{id}/accept — buyurtmani qabul qilish.
  ///
  /// [body] = { lines: [ { line_id, expiry_date, markup_percent } ] }
  Future<Map<String, dynamic>> acceptOrder({
    required String orderId,
    required Map<String, dynamic> body,
  }) async {
    final response = await _dio.patch<Map<String, dynamic>>(
      '/marketplace/orders/$orderId/accept',
      data: body,
    );
    return response.data!;
  }
}

