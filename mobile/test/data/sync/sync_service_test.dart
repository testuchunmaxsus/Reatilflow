import 'dart:convert';

import 'package:drift/native.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:retail_mobile/data/local/dao/outbox_dao.dart';
import 'package:retail_mobile/data/local/dao/sync_cursor_dao.dart';
import 'package:retail_mobile/data/local/database.dart';
import 'package:retail_mobile/data/remote/api_client.dart';
import 'package:retail_mobile/data/remote/models/sync_models.dart';
import 'package:retail_mobile/data/sync/sync_service.dart';
import 'package:retail_mobile/features/orders/order_repository.dart';

class MockApiClient extends Mock implements ApiClient {}

class FakeSyncPushRequest extends Fake implements SyncPushRequest {}

AppDatabase _makeDb() => AppDatabase.forTesting(NativeDatabase.memory());

void _registerFallbacks() {
  registerFallbackValue(FakeSyncPushRequest());
}

void main() {
  setUpAll(_registerFallbacks);

  group('SyncService — push', () {
    late AppDatabase db;
    late MockApiClient mockApi;
    late SyncService syncService;
    late OutboxDao outboxDao;

    setUp(() {
      db = _makeDb();
      mockApi = MockApiClient();
      syncService = SyncService(db: db, apiClient: mockApi);
      outboxDao = OutboxDao(db);
    });
    tearDown(() => db.close());

    test("outbox bo'sh bo'lsa push success qaytaradi", () async {
      final result = await syncService.push();
      expect(result, equals(SyncResult.success));
      verifyNever(() => mockApi.syncPush(any()));
    });

    test('applied op outbox dan o\'chiriladi', () async {
      await outboxDao.insertOp(
        OutboxQueueCompanion.insert(
          opType: 'order.create',
          clientUuid: 'uuid-applied-001',
          payload: jsonEncode({
            'store_id': 's1',
            'lines': [
              {'product_id': 'p1', 'qty': '2'},
            ],
          }),
        ),
      );

      when(() => mockApi.syncPush(any())).thenAnswer(
        (_) async => const SyncPushResponse(
          results: [
            SyncOpResult(
              clientUuid: 'uuid-applied-001',
              status: 'applied',
              serverId: 'server-order-001',
            ),
          ],
        ),
      );

      final result = await syncService.push();
      expect(result, equals(SyncResult.success));

      final pending = await outboxDao.getPending();
      expect(pending, isEmpty);
    });

    test("duplicate op ham outbox dan o'chiriladi", () async {
      await outboxDao.insertOp(
        OutboxQueueCompanion.insert(
          opType: 'order.create',
          clientUuid: 'uuid-dup-001',
          payload: '{"store_id":"s1","lines":[]}',
        ),
      );

      when(() => mockApi.syncPush(any())).thenAnswer(
        (_) async => const SyncPushResponse(
          results: [
            SyncOpResult(
              clientUuid: 'uuid-dup-001',
              status: 'duplicate',
              serverId: 'server-order-002',
            ),
          ],
        ),
      );

      await syncService.push();

      final pending = await outboxDao.getPending();
      expect(pending, isEmpty);
    });

    test('conflict op pending da qolmaydi, conflict statusga o\'tadi', () async {
      await outboxDao.insertOp(
        OutboxQueueCompanion.insert(
          opType: 'order.create',
          clientUuid: 'uuid-conflict-001',
          payload: '{}',
        ),
      );

      when(() => mockApi.syncPush(any())).thenAnswer(
        (_) async => const SyncPushResponse(
          results: [
            SyncOpResult(
              clientUuid: 'uuid-conflict-001',
              status: 'conflict',
              messageKey: 'sync.idor_blocked',
            ),
          ],
        ),
      );

      await syncService.push();

      final pending = await outboxDao.getPending();
      expect(pending, isEmpty);

      final item = await outboxDao.getByClientUuid('uuid-conflict-001');
      expect(item?.status, equals('conflict'));
    });

    test('tarmoq xatosida networkError qaytaradi', () async {
      await outboxDao.insertOp(
        OutboxQueueCompanion.insert(
          opType: 'order.create',
          clientUuid: 'uuid-net-001',
          payload: '{}',
        ),
      );

      when(() => mockApi.syncPush(any())).thenThrow(
        Exception('Connection refused'),
      );

      final result = await syncService.push();
      expect(result, equals(SyncResult.networkError));

      final pending = await outboxDao.getPending();
      expect(pending.length, equals(1));
    });
  });

  group('SyncService — pull', () {
    late AppDatabase db;
    late MockApiClient mockApi;
    late SyncService syncService;
    late SyncCursorDao cursorDao;

    setUp(() {
      db = _makeDb();
      mockApi = MockApiClient();
      syncService = SyncService(db: db, apiClient: mockApi);
      cursorDao = SyncCursorDao(db);
    });
    tearDown(() => db.close());

    test('pull since=0 dan boshlanadi va cursor yangilanadi', () async {
      when(
        () => mockApi.syncPull(
          since: any(named: 'since'),
        ),
      ).thenAnswer(
        (_) async => const SyncPullResponse(
          changes: [],
          nextCursor: 42,
          hasMore: false,
        ),
      );

      await syncService.pull();

      expect(await cursorDao.getLastSeq(), equals(42));
    });

    test("has_more true bo'lsa pagination davom etadi", () async {
      var callCount = 0;

      when(
        () => mockApi.syncPull(
          since: any(named: 'since'),
        ),
      ).thenAnswer((_) async {
        callCount++;
        if (callCount == 1) {
          return const SyncPullResponse(
            changes: [],
            nextCursor: 50,
            hasMore: true,
          );
        }
        return const SyncPullResponse(
          changes: [],
          nextCursor: 100,
          hasMore: false,
        );
      });

      await syncService.pull();

      expect(callCount, equals(2));
      expect(await cursorDao.getLastSeq(), equals(100));
    });

    test("product o'zgarishi lokal bazaga upsert qilinadi", () async {
      when(
        () => mockApi.syncPull(
          since: any(named: 'since'),
        ),
      ).thenAnswer(
        // ignore: prefer_const_constructors
        (_) async => SyncPullResponse(
          changes: [
            // ignore: prefer_const_constructors
            ChangeItem(
              entityType: 'product',
              entityId: 'prod-001',
              eventType: 'product.updated',
              seq: 10,
              snapshot: <String, dynamic>{
                'id': 'prod-001',
                'name_uz': 'Non',
                'name_ru': 'Хлеб',
                'unit': 'dona',
                'is_active': true,
                'version': 2,
                'created_at': '2026-01-01T00:00:00',
                'updated_at': '2026-06-18T00:00:00',
              },
            ),
          ],
          nextCursor: 10,
          hasMore: false,
        ),
      );

      await syncService.pull();

      final products = await db.select(db.products).get();
      expect(products.length, equals(1));
      expect(products.first.nameUz, equals('Non'));
      expect(products.first.version, equals(2));
    });

    test("tarmoq xatosida networkError qaytaradi, cursor o'zgarmaydi", () async {
      when(
        () => mockApi.syncPull(
          since: any(named: 'since'),
        ),
      ).thenThrow(Exception('Timeout'));

      final result = await syncService.pull();
      expect(result, equals(SyncResult.networkError));
      expect(await cursorDao.getLastSeq(), equals(0));
    });
  });

  group('client_uuid generatsiyasi', () {
    test('har buyurtmada yangi UUID generatsiya qilinadi', () async {
      final db = _makeDb();
      final repo = OrderRepository(db: db);

      final results = await Future.wait([
        repo.createOrder(
          storeId: 's1',
          agentId: 'a1',
          lines: const [OrderLineInput(productId: 'p1', qty: 1)],
        ),
        repo.createOrder(
          storeId: 's1',
          agentId: 'a1',
          lines: const [OrderLineInput(productId: 'p1', qty: 1)],
        ),
        repo.createOrder(
          storeId: 's1',
          agentId: 'a1',
          lines: const [OrderLineInput(productId: 'p1', qty: 1)],
        ),
      ]);

      final uuids = results.map((r) => r.clientUuid).toSet();
      expect(uuids.length, equals(3));

      for (final uuid in uuids) {
        expect(
          RegExp(
            r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
          ).hasMatch(uuid),
          isTrue,
          reason: 'UUID v4 format emas: $uuid',
        );
      }

      await db.close();
    });
  });
}
