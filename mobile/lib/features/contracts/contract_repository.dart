import 'dart:convert';

import 'package:drift/drift.dart';
import 'package:uuid/uuid.dart';

import '../../data/local/dao/outbox_dao.dart';
import '../../data/local/database.dart';
import '../../data/remote/api_client.dart';
import 'contract_models.dart';

/// Shartnoma repository.
///
/// Yaratish — offline-first (outbox `contract.create`).
/// O'qish — online GET /contracts?store_id=... (server-avtoritar).
class ContractRepository {
  ContractRepository({
    required AppDatabase db,
    required ApiClient apiClient,
  })  : _api = apiClient,
        _outboxDao = OutboxDao(db);

  final ApiClient _api;
  final OutboxDao _outboxDao;
  static const Uuid _uuid = Uuid();

  /// Yangi shartnoma yaratish — OFFLINE-FIRST.
  ///
  /// outbox'ga `contract.create` yozadi.
  /// supplier_enterprise_id YUBORILMAYDI — server agent tokenidan aniqlaydi.
  Future<String> createContract(CreateContractRequest request) async {
    final clientUuid = _uuid.v4();
    final now = DateTime.now();

    final payload = <String, dynamic>{
      'client_uuid': clientUuid,
      ...request.toJson(),
    };

    await _outboxDao.insertOp(
      OutboxQueueCompanion.insert(
        opType: 'contract.create',
        clientUuid: clientUuid,
        payload: jsonEncode(payload),
        createdAt: Value(now),
      ),
    );

    return clientUuid;
  }

  /// Shartnomalar ro'yxati — online GET /contracts?store_id=...
  ///
  /// Tarmoq mavjud bo'lmasa [Exception] chiqaradi (caller boshqaradi).
  Future<List<Contract>> getContracts({required String storeId}) async {
    final response = await _api.dio.get<dynamic>(
      '/contracts',
      queryParameters: {'store_id': storeId},
    );
    final list = _toList(response.data);
    return list
        .map((e) => Contract.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// Pending outbox yozuvlari (faqat contract.create, ushbu storeId uchun).
  Future<List<PendingContract>> getPendingContracts(String storeId) async {
    final all = await _outboxDao.getPending();
    final result = <PendingContract>[];
    for (final op in all) {
      if (op.opType != 'contract.create') continue;
      try {
        final payload = jsonDecode(op.payload) as Map<String, dynamic>;
        if (payload['store_id'] != storeId) continue;
        result.add(
          PendingContract(
            clientUuid: op.clientUuid,
            storeId: payload['store_id'] as String? ?? storeId,
            number: payload['number'] as String? ?? '',
            validFrom: DateTime.tryParse(
                    payload['valid_from'] as String? ?? '') ??
                op.createdAt,
            validTo: DateTime.tryParse(
                    payload['valid_to'] as String? ?? '') ??
                op.createdAt,
            outboxStatus: op.status,
            createdAt: op.createdAt,
          ),
        );
      } catch (_) {
        // JSON parse xatosi — o'tkazib yuboramiz
      }
    }
    return result;
  }

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
