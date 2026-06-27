import 'dart:convert';

import 'package:drift/drift.dart';

import '../local/dao/orders_dao.dart';
import '../local/dao/outbox_dao.dart';
import '../local/dao/products_dao.dart';
import '../local/dao/stores_dao.dart';
import '../local/dao/sync_cursor_dao.dart';
import '../local/database.dart';
import '../remote/api_client.dart';
import '../remote/models/sync_models.dart';

/// Sync natijasi
enum SyncResult { success, partial, networkError, authError }

/// RETAIL offline-first sync yadrosi.
///
/// Push oqimi:
///   1. outbox_queue dan pending op'larni batch olish (max 50)
///   2. POST /sync/push ga yuborish
///   3. Har op uchun natija: applied → outbox ni tozala + order.server_id yangilab qo'y;
///      duplicate → o'chirish; conflict/error → xato belgilab qo'y.
///
/// Pull oqimi:
///   1. sync_cursor.last_seq olish (0 = birinchi pull)
///   2. GET /sync/pull?since=last_seq
///   3. changes[] → entity_type bo'yicha lokal upsert
///   4. next_cursor saqlash; has_more bo'lsa takrorla
///
/// UI hech qachon to'g'ridan-to'g'ri bu klassni chaqirmaydi — SyncNotifier orqali.
class SyncService {
  SyncService({
    required AppDatabase db,
    required ApiClient apiClient,
  })  : _apiClient = apiClient,
        _outboxDao = OutboxDao(db),
        _syncCursorDao = SyncCursorDao(db),
        _productsDao = ProductsDao(db),
        _storesDao = StoresDao(db),
        _ordersDao = OrdersDao(db);

  final ApiClient _apiClient;
  final OutboxDao _outboxDao;
  final SyncCursorDao _syncCursorDao;
  final ProductsDao _productsDao;
  final StoresDao _storesDao;
  final OrdersDao _ordersDao;

  static const int _pushBatchSize = 50;

  // ============================================================
  // PUSH
  // ============================================================

  /// Outbox dagi barcha pending op'larni serverga yuboradi.
  /// Tarmoq xatosi bo'lsa [SyncResult.networkError] qaytaradi.
  Future<SyncResult> push() async {
    final pending = await _outboxDao.getPending();
    if (pending.isEmpty) return SyncResult.success;

    SyncResult lastError = SyncResult.success;

    // Batch bo'lib yuborish
    for (int i = 0; i < pending.length; i += _pushBatchSize) {
      final batch = pending.skip(i).take(_pushBatchSize).toList();
      final result = await _pushBatch(batch);
      if (result != SyncResult.success) {
        lastError = result;
        if (result == SyncResult.authError) return SyncResult.authError;
        // networkError — keyingi batch uchun to'xtatish
        break;
      }
    }

    // Muvaffaqiyatli op'larni tozalash
    await _outboxDao.deleteApplied();

    // partial = ba'zi op'lar server tomonida conflict/error bo'ldi
    // networkError = tarmoq bilan bog'liq muammo
    return lastError;
  }

  Future<SyncResult> _pushBatch(List<OutboxQueueData> batch) async {
    final ops = batch
        .map(
          (item) => SyncOp(
            opType: item.opType,
            clientUuid: item.clientUuid,
            payload: jsonDecode(item.payload) as Map<String, dynamic>,
          ),
        )
        .toList();

    SyncPushResponse response;
    try {
      response = await _apiClient.syncPush(SyncPushRequest(ops: ops));
    } on Exception catch (e) {
      // Tarmoq/timeout xatosi
      final isAuth = e.toString().contains('401');
      return isAuth ? SyncResult.authError : SyncResult.networkError;
    }

    // Har op natijasini qayta ishlash
    for (final result in response.results) {
      final item = batch.firstWhere(
        (b) => b.clientUuid == result.clientUuid,
        orElse: () => batch.first, // himoya: topilmasa birinchisi
      );

      switch (result.status) {
        case 'applied':
          await _outboxDao.updateStatus(
            item.id,
            status: 'applied',
            responseData: result.serverId,
          );
          // Buyurtma uchun server_id saqla
          if (item.opType == 'order.create' && result.serverId != null) {
            await _ordersDao.updateSyncStatus(
              item.clientUuid,
              status: 'synced',
              serverId: result.serverId,
            );
          }
          // marketplace_order.create — applied (server_id ixtiyoriy)
          // contract.create / store.assign_agent — applied, outbox tozalanadi
          // Bu op'lar uchun lokal jadvalda server_id kerak emas (outbox yetarli)

        case 'duplicate':
          // Avval yuborilgan — o'chirish (idempotent)
          await _outboxDao.updateStatus(item.id, status: 'duplicate');
          if (item.opType == 'order.create' && result.serverId != null) {
            await _ordersDao.updateSyncStatus(
              item.clientUuid,
              status: 'synced',
              serverId: result.serverId,
            );
          }
          // marketplace_order.create duplicate — outbox deleteApplied tozalaydi

        case 'conflict':
          // IDOR yoki boshqa aktor — conflict belgilab qo'y
          await _outboxDao.updateStatus(
            item.id,
            status: 'conflict',
            responseData: result.messageKey,
          );

        case 'error':
          await _outboxDao.updateStatus(
            item.id,
            status: 'error',
            responseData: result.messageKey,
          );
          await _outboxDao.incrementAttempts(item.id);
      }
    }

    return SyncResult.success;
  }

  // ============================================================
  // PULL
  // ============================================================

  /// Serverdan delta o'zgarishlarni tortib lokal bazaga upsert qiladi.
  /// has_more bo'lsa sahifalar bo'yicha to'liq tortib oladi.
  Future<SyncResult> pull() async {
    int since = await _syncCursorDao.getLastSeq();

    try {
      bool hasMore = true;
      while (hasMore) {
        final response = await _apiClient.syncPull(since: since);

        if (response.changes.isNotEmpty) {
          await _applyChanges(response.changes);
        }

        // Kursor yangilash — har sahifadan keyin
        if (response.nextCursor > since) {
          await _syncCursorDao.updateLastSeq(response.nextCursor);
          since = response.nextCursor;
        }

        hasMore = response.hasMore;
      }

      return SyncResult.success;
    } on Exception catch (e) {
      final isAuth = e.toString().contains('401');
      return isAuth ? SyncResult.authError : SyncResult.networkError;
    }
  }

  /// O'zgarishlarni entity_type bo'yicha lokal bazaga upsert qiladi.
  Future<void> _applyChanges(List<ChangeItem> changes) async {
    // Batch bo'yicha guruhlash
    final productChanges = <ChangeItem>[];
    final storeChanges = <ChangeItem>[];
    final orderChanges = <ChangeItem>[];

    for (final change in changes) {
      switch (change.entityType) {
        case 'product':
        case 'catalog':
          productChanges.add(change);
        case 'store':
          storeChanges.add(change);
        case 'order':
          orderChanges.add(change);
        // price_segment, promo, order_template va boshqalar
        // kelajakda qo'shiladi (T21/T20)
      }
    }

    if (productChanges.isNotEmpty) {
      await _applyProductChanges(productChanges);
    }
    if (storeChanges.isNotEmpty) {
      await _applyStoreChanges(storeChanges);
    }
    if (orderChanges.isNotEmpty) {
      await _applyOrderChanges(orderChanges);
    }
  }

  Future<void> _applyProductChanges(List<ChangeItem> changes) async {
    final companions = <ProductsCompanion>[];
    for (final change in changes) {
      final s = change.snapshot;
      companions.add(
        ProductsCompanion(
          id: Value(_str(s, 'id')),
          nameUz: Value(_str(s, 'name_uz')),
          nameRu: Value(_strOpt(s, 'name_ru')),
          sku: Value(_strOpt(s, 'sku')),
          barcode: Value(_strOpt(s, 'barcode')),
          mxikCode: Value(_strOpt(s, 'mxik_code')),
          unit: Value(_str(s, 'unit', fallback: 'dona')),
          categoryId: Value(_strOpt(s, 'category_id')),
          photoUrl: Value(_strOpt(s, 'photo_url')),
          isActive: Value(s['is_active'] as bool? ?? true),
          branchScope: Value(_strOpt(s, 'branch_scope')),
          version: Value((s['version'] as int?) ?? 1),
          createdAt: Value(_parseDate(s, 'created_at')),
          updatedAt: Value(_parseDate(s, 'updated_at')),
          deletedAt: Value(_parseDateOpt(s, 'deleted_at')),
          cachedAt: Value(DateTime.now()),
        ),
      );
    }
    await _productsDao.upsertBatch(companions);
  }

  Future<void> _applyStoreChanges(List<ChangeItem> changes) async {
    final companions = <StoresCompanion>[];
    for (final change in changes) {
      final s = change.snapshot;
      companions.add(
        StoresCompanion(
          id: Value(_str(s, 'id')),
          name: Value(_str(s, 'name')),
          inn: Value(_strOpt(s, 'inn')),
          phone: Value(_strOpt(s, 'phone')),
          gpsLat: Value(s['gps_lat'] as double?),
          gpsLng: Value(s['gps_lng'] as double?),
          address: Value(_strOpt(s, 'address')),
          segmentId: Value(_strOpt(s, 'segment_id')),
          agentId: Value(_strOpt(s, 'agent_id')),
          branchId: Value(_strOpt(s, 'branch_id')),
          creditLimit: Value((s['credit_limit'] as num?)?.toDouble()),
          version: Value((s['version'] as int?) ?? 1),
          createdAt: Value(_parseDate(s, 'created_at')),
          updatedAt: Value(_parseDate(s, 'updated_at')),
          deletedAt: Value(_parseDateOpt(s, 'deleted_at')),
          cachedAt: Value(DateTime.now()),
        ),
      );
    }
    await _storesDao.upsertBatch(companions);
  }

  Future<void> _applyOrderChanges(List<ChangeItem> changes) async {
    for (final change in changes) {
      final s = change.snapshot;
      final serverId = _str(s, 'id');

      // Lokal order ni client_uuid bo'yicha topish
      final localOrder = await (
        // Drift'da custom where — server_id yoki clientUuid
        _ordersDao.getById(serverId)
      );

      if (localOrder != null) {
        // Mavjud — yangilash (holat mashinasi: server-avtoritar)
        await _ordersDao.updateOrder(
          OrdersCompanion(
            id: Value(localOrder.id),
            status: Value(_str(s, 'status', fallback: localOrder.status)),
            version: Value((s['version'] as int?) ?? localOrder.version),
            serverId: Value(serverId),
            syncStatus: const Value('synced'),
            updatedAt: Value(DateTime.now()),
          ),
        );
      }
      // Agar topilmasa (boshqa agentning buyurtmasi) — hozirda saqlanmaydi
      // T21 da agent boshqa agentlar buyurtmalarini ko'rish kerak bo'lsa qo'shiladi
    }
  }

  // ============================================================
  // FULL SYNC
  // ============================================================

  /// Push + pull (birgalikda)
  Future<SyncResult> sync() async {
    final pushResult = await push();
    if (pushResult == SyncResult.authError) return SyncResult.authError;

    final pullResult = await pull();
    if (pullResult == SyncResult.authError) return SyncResult.authError;

    if (pushResult == SyncResult.partial ||
        pullResult == SyncResult.networkError) {
      return SyncResult.partial;
    }

    return SyncResult.success;
  }

  // ============================================================
  // Yordamchi metodlar
  // ============================================================

  String _str(
    Map<String, dynamic> s,
    String key, {
    String fallback = '',
  }) {
    final v = s[key];
    if (v is String) return v;
    return fallback;
  }

  String? _strOpt(Map<String, dynamic> s, String key) =>
      s[key] as String?;

  DateTime _parseDate(Map<String, dynamic> s, String key) {
    final v = s[key];
    if (v == null) return DateTime.now();
    if (v is String) return DateTime.tryParse(v) ?? DateTime.now();
    return DateTime.now();
  }

  DateTime? _parseDateOpt(Map<String, dynamic> s, String key) {
    final v = s[key];
    if (v == null) return null;
    if (v is String) return DateTime.tryParse(v);
    return null;
  }
}
