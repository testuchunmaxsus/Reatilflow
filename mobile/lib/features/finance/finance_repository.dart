import '../../data/remote/api_client.dart';
import 'finance_models.dart';

/// Finance repository — GET /finance/balance/{store_id}, GET /finance/ledger.
///
/// RBAC (STOCK_FINANCE.md §2.4):
///   accountant → barcha do'konlar balansi va ledger.
///   Boshqa rollar uchun backend 403/404 qaytaradi.
///
/// Offline ko'magi yo'q — moliyaviy ma'lumotlar real-time o'qiladi (ADR §3.4).
class FinanceRepository {
  FinanceRepository({required ApiClient apiClient}) : _api = apiClient;

  final ApiClient _api;

  // --------------------------------------------------------------------------
  // Balans

  /// GET /finance/balance/{store_id} — do'kon moliyaviy balansi.
  ///
  /// [storeId] — do'kon UUID.
  Future<FinanceBalance> getBalance(String storeId) async {
    final response = await _api.dio.get<Map<String, dynamic>>(
      '/finance/balance/$storeId',
    );
    return FinanceBalance.fromJson(response.data!);
  }

  // --------------------------------------------------------------------------
  // Ledger

  /// GET /finance/ledger — yozuvlar ro'yxati (paginated).
  ///
  /// [storeId] — do'kon UUID filtri (ixtiyoriy).
  /// [entryType] — 'debit' | 'credit' filtri (ixtiyoriy).
  /// [limit] — sahifa hajmi (default 20).
  /// [offset] — o'tkazib yuborish (default 0).
  Future<LedgerPage> getLedger({
    String? storeId,
    String? entryType,
    int limit = 20,
    int offset = 0,
  }) async {
    final params = <String, dynamic>{
      'limit': limit,
      'offset': offset,
      if (storeId != null && storeId.isNotEmpty) 'store_id': storeId,
      if (entryType != null && entryType.isNotEmpty) 'entry_type': entryType,
    };

    final response = await _api.dio.get<Map<String, dynamic>>(
      '/finance/ledger',
      queryParameters: params,
    );
    return LedgerPage.fromJson(response.data!);
  }
}
