import 'dart:convert';

import 'package:drift/drift.dart';
import 'package:uuid/uuid.dart';

import '../../data/local/dao/outbox_dao.dart';
import '../../data/local/dao/stores_dao.dart';
import '../../data/local/database.dart';
import '../../data/remote/api_client.dart';

/// Do'kon tahrirlash natijasi
class StoreResult {
  const StoreResult({required this.storeId, required this.clientUuid});
  final String storeId;
  final String clientUuid;
}

/// Do'kon repository — create (API to'g'ridan) va update (outbox orqali).
///
/// Qoidalar (mobil):
///   - API chaqiruvlar api_client.dart'ga yangi metod qo'shmasdan,
///     dio.post / dio.patch orqali to'g'ridan repo ichida amalga oshiriladi.
///   - updateStore offline-first: lokal yozib, outbox'ga qo'shadi.
///   - createStore onlayn: to'g'ridan POST, keyin sync trigger (mavjud oqim saqlanadi).
class StoreRepository {
  StoreRepository({
    required AppDatabase db,
    required ApiClient apiClient,
  })  : _apiClient = apiClient,
        _storesDao = StoresDao(db),
        _outboxDao = OutboxDao(db),
        _db = db;

  final ApiClient _apiClient;
  final StoresDao _storesDao;
  final OutboxDao _outboxDao;
  final AppDatabase _db;

  static const Uuid _uuid = Uuid();

  /// Yangi do'kon yaratish — POST /customers/stores.
  ///
  /// Mavjud onlayn oqimni saqlab, yangi maydonlar qo'shildi:
  /// address, inn, inps, credit_limit, segment_id.
  Future<Map<String, dynamic>> createStore({
    required String name,
    required String ownerName,
    required String phone,
    required String gpsLat,
    required String gpsLng,
    String? address,
    String? inn,
    String? inps,
    double? creditLimit,
    String? segmentId,
  }) async {
    final body = <String, dynamic>{
      'name': name,
      'owner_name': ownerName,
      'phone': phone,
      'gps_lat': gpsLat,
      'gps_lng': gpsLng,
      if (address != null && address.isNotEmpty) 'address': address,
      if (inn != null && inn.isNotEmpty) 'inn': inn,
      if (inps != null && inps.isNotEmpty) 'inps': inps,
      if (creditLimit != null) 'credit_limit': creditLimit,
      if (segmentId != null && segmentId.isNotEmpty) 'segment_id': segmentId,
    };

    // generic dio.post orqali — api_client'ga yangi metod qo'shilmaydi
    final response = await _apiClient.dio.post<Map<String, dynamic>>(
      '/customers/stores',
      data: body,
    );
    return response.data!;
  }

  /// Do'konni tahrirlash — OFFLINE-FIRST.
  ///
  /// 1. Lokal Drift bazasida yangilanadi.
  /// 2. outbox_queue'ga 'store.update' operatsiya yoziladi.
  ///
  /// PATCH /customers/stores/{id} — name/owner_name/phone/address/gps/version.
  Future<StoreResult> updateStore({
    required String storeId,
    required int version,
    String? name,
    String? ownerName,
    String? phone,
    String? address,
    double? gpsLat,
    double? gpsLng,
  }) async {
    final clientUuid = _uuid.v4();
    final now = DateTime.now();

    final payload = <String, dynamic>{
      'store_id': storeId,
      'version': version,
      if (name != null) 'name': name,
      if (ownerName != null) 'owner_name': ownerName,
      if (phone != null) 'phone': phone,
      if (address != null) 'address': address,
      if (gpsLat != null) 'gps_lat': gpsLat,
      if (gpsLng != null) 'gps_lng': gpsLng,
    };

    await _db.transaction(() async {
      // 1. Lokal bazada yangilash
      await _storesDao.upsertFromSync(
        StoresCompanion(
          id: Value(storeId),
          updatedAt: Value(now),
          name: name != null ? Value(name) : const Value.absent(),
          phone: phone != null ? Value(phone) : const Value.absent(),
          address: address != null ? Value(address) : const Value.absent(),
          gpsLat: gpsLat != null ? Value(gpsLat) : const Value.absent(),
          gpsLng: gpsLng != null ? Value(gpsLng) : const Value.absent(),
        ),
      );

      // 2. Outbox'ga qo'shish
      await _outboxDao.insertOp(
        OutboxQueueCompanion.insert(
          opType: 'store.update',
          clientUuid: clientUuid,
          payload: jsonEncode(payload),
          createdAt: Value(now),
        ),
      );
    });

    return StoreResult(storeId: storeId, clientUuid: clientUuid);
  }

  /// Do'konni lokal bazadan ID bo'yicha olish
  Future<Store?> getById(String id) => _storesDao.getById(id);

  /// Agentni do'konga biriktirish — OFFLINE-FIRST.
  ///
  /// outbox'ga 'store.assign_agent' operatsiya yozadi.
  /// Backend: POST /customers/stores/{id}/assign-agent.
  Future<String> assignAgent({
    required String storeId,
    required String agentId,
  }) async {
    final clientUuid = _uuid.v4();
    final now = DateTime.now();

    final payload = <String, dynamic>{
      'store_id': storeId,
      'agent_id': agentId,
    };

    await _outboxDao.insertOp(
      OutboxQueueCompanion.insert(
        opType: 'store.assign_agent',
        clientUuid: clientUuid,
        payload: jsonEncode(payload),
        createdAt: Value(now),
      ),
    );

    // Lokal bazada ham yangilash (offline display uchun)
    await _storesDao.upsertFromSync(
      StoresCompanion(
        id: Value(storeId),
        agentId: Value(agentId),
        updatedAt: Value(now),
      ),
    );

    return clientUuid;
  }
}
