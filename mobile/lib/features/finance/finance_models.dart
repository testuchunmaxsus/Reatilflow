// Finance — modellar va javob tiplari.
//
// Backend endpointlari (STOCK_FINANCE.md §2):
//   GET  /finance/balance/{store_id}  → FinanceBalance
//   GET  /finance/ledger              → LedgerPage
//   POST /finance/ledger              → LedgerEntry
//   POST /finance/ledger/{id}/approve → LedgerEntry

// ---------------------------------------------------------------------------
// Balans

/// GET /finance/balance/{store_id} javobi.
class FinanceBalance {
  const FinanceBalance({
    required this.id,
    required this.storeId,
    required this.balance,
    required this.currency,
    required this.lastRecalcAt,
    required this.version,
  });

  factory FinanceBalance.fromJson(Map<String, dynamic> json) {
    return FinanceBalance(
      id: json['id'] as String? ?? '',
      storeId: json['store_id'] as String? ?? '',
      balance: json['balance'] as String? ?? '0.00',
      currency: json['currency'] as String? ?? 'UZS',
      lastRecalcAt: json['last_recalc_at'] != null
          ? DateTime.tryParse(json['last_recalc_at'] as String) ??
              DateTime.now()
          : DateTime.now(),
      version: json['version'] as int? ?? 1,
    );
  }

  final String id;
  final String storeId;

  /// Qoldiq — string decimal (server formati). `balance > 0` = qarzdor.
  final String balance;
  final String currency;
  final DateTime lastRecalcAt;
  final int version;

  /// Raqamli qoldiq (UI uchun).
  double get balanceAmount => double.tryParse(balance) ?? 0.0;

  /// Qarzdorlik ko'rsatkichi.
  bool get isDebt => balanceAmount > 0;
}

// ---------------------------------------------------------------------------
// Ledger yozuvi

/// Yozuv turi: debit | credit (STOCK_FINANCE.md §2.2).
enum LedgerEntryType {
  debit,
  credit;

  static LedgerEntryType fromString(String s) => switch (s) {
        'debit' => debit,
        'credit' => credit,
        _ => debit,
      };

  String get label => switch (this) {
        debit => 'Debet',
        credit => 'Kredit',
      };
}

/// Ledger yozuv holati (STOCK_FINANCE.md §2.2).
enum LedgerEntryStatus {
  pending,
  approved;

  static LedgerEntryStatus fromString(String s) => switch (s) {
        'approved' => approved,
        _ => pending,
      };

  String get label => switch (this) {
        pending => 'Kutilmoqda',
        approved => 'Tasdiqlangan',
      };
}

/// GET /finance/ledger — bitta yozuv.
class LedgerEntry {
  const LedgerEntry({
    required this.id,
    required this.storeId,
    required this.type,
    required this.amount,
    required this.currency,
    required this.entryDate,
    required this.createdAt,
    required this.status,
    this.refType,
    this.refId,
    this.createdBy,
    this.clientUuid,
  });

  factory LedgerEntry.fromJson(Map<String, dynamic> json) {
    return LedgerEntry(
      id: json['id'] as String? ?? '',
      storeId: json['store_id'] as String? ?? '',
      type: LedgerEntryType.fromString(json['type'] as String? ?? 'debit'),
      amount: json['amount'] as String? ?? '0.00',
      currency: json['currency'] as String? ?? 'UZS',
      entryDate: json['entry_date'] != null
          ? DateTime.tryParse(json['entry_date'] as String) ?? DateTime.now()
          : DateTime.now(),
      createdAt: json['created_at'] != null
          ? DateTime.tryParse(json['created_at'] as String) ?? DateTime.now()
          : DateTime.now(),
      status: LedgerEntryStatus.fromString(
          json['status'] as String? ?? 'pending'),
      refType: json['ref_type'] as String?,
      refId: json['ref_id'] as String?,
      createdBy: json['created_by'] as String?,
      clientUuid: json['client_uuid'] as String?,
    );
  }

  final String id;
  final String storeId;
  final LedgerEntryType type;

  /// Miqdor — string decimal (server formati).
  final String amount;
  final String currency;
  final DateTime entryDate;
  final DateTime createdAt;
  final LedgerEntryStatus status;
  final String? refType;
  final String? refId;
  final String? createdBy;
  final String? clientUuid;

  /// Raqamli miqdor (UI uchun).
  double get amountValue => double.tryParse(amount) ?? 0.0;

  /// Tasdiqlash mumkinmi?
  bool get canApprove => status == LedgerEntryStatus.pending;
}

// ---------------------------------------------------------------------------
// Ledger yaratish so'rovi

/// POST /finance/ledger — yangi yozuv so'rovi (STOCK_FINANCE.md §2.3).
class CreateLedgerRequest {
  const CreateLedgerRequest({
    required this.storeId,
    required this.type,
    required this.amount,
    required this.currency,
    required this.validFrom,
    this.refType,
    this.refId,
  });

  final String storeId;
  final LedgerEntryType type;

  /// Miqdor — musbat son (server sign ni type orqali aniqlaydi).
  final double amount;
  final String currency;
  final DateTime validFrom;
  final String? refType;
  final String? refId;

  Map<String, dynamic> toJson() => {
        'store_id': storeId,
        'type': type.name,
        'amount': amount.toStringAsFixed(2),
        'currency': currency,
        'valid_from': validFrom.toIso8601String().split('T').first,
        if (refType != null && refType!.isNotEmpty) 'ref_type': refType,
        if (refId != null && refId!.isNotEmpty) 'ref_id': refId,
      };
}

// ---------------------------------------------------------------------------
// Paginatsiya

/// GET /finance/ledger — paginated javob.
class LedgerPage {
  const LedgerPage({
    required this.items,
    required this.total,
    required this.limit,
    required this.offset,
  });

  factory LedgerPage.fromJson(Map<String, dynamic> json) {
    final rawItems = json['items'] as List<dynamic>? ?? [];
    return LedgerPage(
      items: rawItems
          .map((e) => LedgerEntry.fromJson(e as Map<String, dynamic>))
          .toList(),
      total: json['total'] as int? ?? 0,
      limit: json['limit'] as int? ?? 20,
      offset: json['offset'] as int? ?? 0,
    );
  }

  final List<LedgerEntry> items;
  final int total;
  final int limit;
  final int offset;

  bool get hasMore => offset + items.length < total;
}
