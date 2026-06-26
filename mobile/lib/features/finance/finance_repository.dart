import '../../data/remote/api_client.dart';
import 'finance_models.dart';

/// Finance repository — ledger CRUD + balans.
///
/// RBAC (STOCK_FINANCE.md §2.4):
///   accountant → barcha do'konlar balansi va ledger.
///   Boshqa rollar uchun backend 403/404 qaytaradi.
///
/// Offline ko'magi yo'q — moliyaviy ma'lumotlar real-time o'qiladi (ADR §3.4).
///
/// Yangi endpointlar:
///   POST /finance/ledger             → LedgerEntry (yaratish)
///   POST /finance/ledger/{id}/approve → LedgerEntry (tasdiqlash)
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

  // --------------------------------------------------------------------------
  // Ledger yozuv yaratish

  /// POST /finance/ledger — yangi yozuv yaratish (STOCK_FINANCE.md §2.3).
  ///
  /// Faqat accountant roli uchun (backend RBAC tekshiradi).
  /// [request] — CreateLedgerRequest: store_id, type, amount, currency, valid_from.
  Future<LedgerEntry> createLedger(CreateLedgerRequest request) async {
    final response = await _api.dio.post<Map<String, dynamic>>(
      '/finance/ledger',
      data: request.toJson(),
    );
    return LedgerEntry.fromJson(response.data!);
  }

  // --------------------------------------------------------------------------
  // Ledger yozuvni tasdiqlash

  /// POST /finance/ledger/{id}/approve — yozuvni tasdiqlash.
  ///
  /// Faqat accountant roli uchun (backend RBAC tekshiradi).
  /// [entryId] — tasdiqlash kerak bo'lgan yozuv UUID.
  /// Qaytaradi yangilangan [LedgerEntry] (status: approved).
  Future<LedgerEntry> approveLedger(String entryId) async {
    final response = await _api.dio.post<Map<String, dynamic>>(
      '/finance/ledger/$entryId/approve',
    );
    return LedgerEntry.fromJson(response.data!);
  }
}
