// Contracts — modellar.
//
// Backend endpointlari:
//   POST /contracts                    → Contract (yaratish)
//   GET  /contracts?store_id=...       → Contract ro'yxati

/// Shartnoma holati.
enum ContractStatus {
  active,
  expired,
  pending,
  cancelled;

  static ContractStatus fromString(String s) => switch (s) {
        'active' => active,
        'expired' => expired,
        'pending' => pending,
        'cancelled' => cancelled,
        _ => pending,
      };

  String get label => switch (this) {
        active => 'Faol',
        expired => 'Muddati tugagan',
        pending => 'Kutilmoqda',
        cancelled => 'Bekor qilingan',
      };
}

/// GET /contracts — bitta shartnoma.
class Contract {
  const Contract({
    required this.id,
    required this.storeId,
    required this.supplierEnterpriseId,
    required this.supplierEnterpriseName,
    required this.number,
    required this.validFrom,
    required this.validTo,
    required this.status,
    this.createdAt,
  });

  factory Contract.fromJson(Map<String, dynamic> json) {
    return Contract(
      id: json['id'] as String? ?? '',
      storeId: json['store_id'] as String? ?? '',
      supplierEnterpriseId: json['supplier_enterprise_id'] as String? ?? '',
      supplierEnterpriseName:
          json['supplier_enterprise_name'] as String? ?? '',
      number: json['number'] as String? ?? '',
      validFrom: DateTime.tryParse(json['valid_from'] as String? ?? '') ??
          DateTime.now(),
      validTo:
          DateTime.tryParse(json['valid_to'] as String? ?? '') ?? DateTime.now(),
      status: ContractStatus.fromString(json['status'] as String? ?? 'pending'),
      createdAt: json['created_at'] != null
          ? DateTime.tryParse(json['created_at'] as String)
          : null,
    );
  }

  final String id;
  final String storeId;
  final String supplierEnterpriseId;
  final String supplierEnterpriseName;

  /// Shartnoma raqami (korxona ichida unikal).
  final String number;
  final DateTime validFrom;
  final DateTime validTo;
  final ContractStatus status;
  final DateTime? createdAt;

  bool get isActive => status == ContractStatus.active;

  Map<String, dynamic> toJson() => {
        'id': id,
        'store_id': storeId,
        'supplier_enterprise_id': supplierEnterpriseId,
        'supplier_enterprise_name': supplierEnterpriseName,
        'number': number,
        'valid_from': validFrom.toIso8601String().split('T').first,
        'valid_to': validTo.toIso8601String().split('T').first,
        'status': status.name,
        if (createdAt != null) 'created_at': createdAt!.toIso8601String(),
      };
}

/// POST /contracts so'rovi (outbox payload).
///
/// Narx/supplier_enterprise_id YUBORILMAYDI — server agent tokenidan aniqlaydi.
class CreateContractRequest {
  const CreateContractRequest({
    required this.storeId,
    required this.number,
    required this.validFrom,
    required this.validTo,
  });

  final String storeId;
  final String number;
  final DateTime validFrom;
  final DateTime validTo;

  Map<String, dynamic> toJson() => {
        'store_id': storeId,
        'number': number,
        'valid_from': validFrom.toIso8601String().split('T').first,
        'valid_to': validTo.toIso8601String().split('T').first,
        // supplier_enterprise_id YUBORILMAYDI — server avtoritar
      };
}

/// Offline pending shartnoma (outbox'dan ko'rsatish uchun).
class PendingContract {
  const PendingContract({
    required this.clientUuid,
    required this.storeId,
    required this.number,
    required this.validFrom,
    required this.validTo,
    required this.outboxStatus,
    required this.createdAt,
  });

  final String clientUuid;
  final String storeId;
  final String number;
  final DateTime validFrom;
  final DateTime validTo;

  /// outbox holati: pending | sent | conflict | error
  final String outboxStatus;
  final DateTime createdAt;

  /// Xatolik xabari ko'rsatiladimi?
  bool get hasError =>
      outboxStatus == 'conflict' || outboxStatus == 'error';
}
