import 'dart:io';

import 'package:dio/dio.dart';

import '../../data/remote/api_client.dart';
import 'marketplace_models.dart';

/// Marketplace repository — server bilan muloqot.
///
/// Cross-tenant browse (supplier katalogi, bannerlar, aksiyalar).
/// Buyurtma yaratish: server-avtoritar, narx YUBORILMAYDI.
/// Qabul qilish: expiry_date + markup_percent → StoreInventory (backend).
class MarketplaceRepository {
  MarketplaceRepository({required ApiClient apiClient}) : _api = apiClient;

  final ApiClient _api;

  // ---------------------------------------------------------------------------
  // Browse

  /// GET /marketplace/banners?limit=N — reklama bannerlari.
  Future<List<MarketplaceBanner>> getBanners({int limit = 5}) async {
    final response = await _api.dio.get<dynamic>(
      '/marketplace/banners',
      queryParameters: {'limit': limit},
    );
    final list = _toList(response.data);
    return list
        .map((e) =>
            MarketplaceBanner.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// GET /marketplace/promos?limit=N — qaynoq aksiyalar.
  Future<List<MarketplacePromo>> getPromos({int limit = 20}) async {
    final response = await _api.dio.get<dynamic>(
      '/marketplace/promos',
      queryParameters: {'limit': limit},
    );
    final list = _toList(response.data);
    return list
        .map((e) =>
            MarketplacePromo.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// GET /marketplace/products — mahsulotlar ro'yxati.
  ///
  /// [search] — nomi/SKU bo'yicha qidiruv.
  /// [supplierEnterpriseId] — supplier filtr.
  Future<List<MarketplaceProduct>> getProducts({
    String? search,
    String? supplierEnterpriseId,
  }) async {
    final params = <String, dynamic>{
      if (search != null && search.isNotEmpty) 'search': search,
      if (supplierEnterpriseId != null && supplierEnterpriseId.isNotEmpty)
        'supplier_enterprise_id': supplierEnterpriseId,
    };
    final response = await _api.dio.get<dynamic>(
      '/marketplace/products',
      queryParameters: params.isEmpty ? null : params,
    );
    final list = _toList(response.data);
    return list
        .map((e) =>
            MarketplaceProduct.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  // ---------------------------------------------------------------------------
  // Orders

  /// POST /marketplace/orders — buyurtma yaratish.
  ///
  /// Faqat product_id + qty yuboriladi (narx YO'Q).
  Future<MarketplaceOrder> createOrder(
      CreateMarketplaceOrderRequest request) async {
    final response = await _api.dio.post<Map<String, dynamic>>(
      '/marketplace/orders',
      data: request.toJson(),
    );
    return MarketplaceOrder.fromJson(response.data!);
  }

  /// GET /marketplace/orders/outgoing — chiquvchi buyurtmalar ro'yxati.
  Future<List<MarketplaceOrder>> getOutgoingOrders() async {
    final response =
        await _api.dio.get<dynamic>('/marketplace/orders/outgoing');
    final list = _toList(response.data);
    return list
        .map((e) =>
            MarketplaceOrder.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// GET /marketplace/orders/{id} — bitta buyurtma.
  Future<MarketplaceOrder> getOrder(String orderId) async {
    final response =
        await _api.dio.get<Map<String, dynamic>>('/marketplace/orders/$orderId');
    return MarketplaceOrder.fromJson(response.data!);
  }

  /// PATCH /marketplace/orders/{id}/accept — buyurtmani qabul qilish.
  ///
  /// Har line uchun expiry_date + markup_percent kiritiladi.
  /// Backend mahsulotlarni StoreInventory ga qo'shadi.
  Future<MarketplaceOrder> acceptOrder({
    required String orderId,
    required AcceptOrderRequest request,
  }) async {
    final response = await _api.dio.patch<Map<String, dynamic>>(
      '/marketplace/orders/$orderId/accept',
      data: request.toJson(),
    );
    return MarketplaceOrder.fromJson(response.data!);
  }

  // ---------------------------------------------------------------------------
  // Kuryer marketplace yetkazish (V2C)

  /// GET /marketplace/orders/deliveries — kuryer o'ziga tayinlangan buyurtmalar.
  ///
  /// Faqat delivering holat, courier_id == joriy foydalanuvchi.
  /// Courier roli uchun modul-gated.
  Future<List<MarketplaceOrder>> getMarketplaceDeliveries() async {
    final response =
        await _api.dio.get<dynamic>('/marketplace/orders/deliveries');
    final list = _toList(response.data);
    return list
        .map((e) =>
            MarketplaceOrder.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// POST /marketplace/orders/{id}/proof-photo — kuryer rasm yuklaydi + deliver.
  ///
  /// [orderId] — yetkaziladigan buyurtma UUID.
  /// [imageFile] — kameradan olingan fayl.
  ///
  /// Backend: rasm MinIO ga yuklanadi, buyurtma delivering → delivered.
  Future<MarketplaceOrder> uploadProofAndDeliver({
    required String orderId,
    required File imageFile,
  }) async {
    final formData = FormData.fromMap({
      'file': await MultipartFile.fromFile(
        imageFile.path,
        filename: 'proof_${orderId.substring(0, 8)}.jpg',
      ),
    });

    final response = await _api.dio.post<Map<String, dynamic>>(
      '/marketplace/orders/$orderId/proof-photo',
      data: formData,
      options: Options(contentType: 'multipart/form-data'),
    );
    return MarketplaceOrder.fromJson(response.data!);
  }

  // ---------------------------------------------------------------------------

  /// Javob turidan qat'i nazar List<dynamic> qaytaradi.
  List<dynamic> _toList(dynamic data) {
    if (data is List) return data;
    if (data is Map<String, dynamic>) {
      return data['items'] as List? ??
          data['data'] as List? ??
          data['results'] as List? ??
          [];
    }
    return [];
  }
}
