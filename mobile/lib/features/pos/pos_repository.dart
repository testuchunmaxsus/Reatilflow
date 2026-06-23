import 'package:dio/dio.dart';

import '../../data/remote/api_client.dart';
import 'pos_models.dart';

/// POS repository — server bilan muloqot.
///
/// Server-avtoritar: narx YUBORILMAYDI, server hisoblaydi.
/// Offline: hozircha online-only; keyingi versiyada outbox qo'shiladi.
///
/// NOTE(v2b-offline): POS sotuv offline navbatga (outbox) qo'shish
/// v2b da rejalashtirilgan. Hozir har doim online sotuv.
class PosRepository {
  PosRepository({required ApiClient apiClient}) : _api = apiClient;

  final ApiClient _api;

  // ---------------------------------------------------------------------------
  // Inventory

  /// GET /marketplace/inventory — mahsulotlar inventari.
  ///
  /// Javobda [InventoryItem.isExpired], [InventoryItem.isNearExpiry],
  /// [InventoryItem.daysToExpiry] bayroqlari mavjud.
  Future<List<InventoryItem>> getInventory() async {
    final response = await _api.dio.get<dynamic>('/marketplace/inventory');
    final data = response.data;

    final List<dynamic> list;
    if (data is List<dynamic>) {
      list = data;
    } else if (data is Map<String, dynamic>) {
      list = data['items'] as List<dynamic>? ?? <dynamic>[];
    } else {
      list = <dynamic>[];
    }

    return list
        .map((e) => InventoryItem.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  // ---------------------------------------------------------------------------
  // POS sotuv

  /// POST /pos/sales — sotuv yaratish.
  ///
  /// Faqat [product_id] va [qty] yuboriladi.
  /// 422 + message_key: "pos.product_expired" → [PosProductExpiredException].
  Future<PosSaleResponse> createSale(PosSaleRequest request) async {
    try {
      final response = await _api.dio.post<Map<String, dynamic>>(
        '/pos/sales',
        data: request.toJson(),
      );
      return PosSaleResponse.fromJson(response.data!);
    } on Object catch (e) {
      // 422 → expired mahsulot bloki
      final expiredErr = _tryParseExpiredError(e);
      if (expiredErr != null) throw expiredErr;
      rethrow;
    }
  }

  // ---------------------------------------------------------------------------
  // Kunlik hisobot

  /// GET /pos/summary?date=YYYY-MM-DD — kunlik sotuv hisoboti.
  ///
  /// [date] — "2026-06-23" formatida. Null bo'lsa bugun.
  Future<PosSummary> getPosSummary({String? date}) async {
    final dateStr = date ?? _todayStr();
    final response = await _api.dio.get<Map<String, dynamic>>(
      '/pos/summary',
      queryParameters: {'date': dateStr},
    );
    return PosSummary.fromJson(response.data!);
  }

  // ---------------------------------------------------------------------------

  String _todayStr() {
    final now = DateTime.now();
    final m = now.month.toString().padLeft(2, '0');
    final d = now.day.toString().padLeft(2, '0');
    return '${now.year}-$m-$d';
  }

  /// Dio 422 + message_key: "pos.product_expired" → [PosProductExpiredException]
  PosProductExpiredException? _tryParseExpiredError(Object error) {
    if (error is DioException) {
      if (error.response?.statusCode == 422) {
        final data = error.response?.data;
        final key = _extractMessageKey(data);
        if (key == 'pos.product_expired') {
          return PosProductExpiredException();
        }
        // Javob stringda bo'lsa ham tekshiramiz
        if (data?.toString().contains('pos.product_expired') == true) {
          return PosProductExpiredException();
        }
      }
    }
    return null;
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
}

/// 422 — mahsulot muddati o'tgan, sotuv rad etildi.
class PosProductExpiredException implements Exception {
  @override
  String toString() =>
      "PosProductExpiredException: mahsulot muddati o'tgan, sotuv mumkin emas";
}
