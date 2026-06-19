import 'dart:convert';

import 'package:drift/drift.dart' hide isNotNull, isNull;
import 'package:drift/native.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:retail_mobile/data/local/dao/deliveries_dao.dart';
import 'package:retail_mobile/data/local/dao/outbox_dao.dart';
import 'package:retail_mobile/data/local/database.dart';
import 'package:retail_mobile/features/attendance/gps_service.dart';
import 'package:retail_mobile/features/delivery/delivery_repository.dart';

AppDatabase _makeDb() => AppDatabase.forTesting(NativeDatabase.memory());

/// Test uchun yetkazish yozuvi yaratish yordamchisi
Future<Delivery> _insertDelivery(
  DeliveriesDao dao, {
  String id = 'delivery-001',
  String orderId = 'order-001',
  String courierId = 'courier-001',
  String status = 'assigned',
  int version = 1,
}) async {
  await dao.upsert(
    DeliveriesCompanion.insert(
      id: id,
      orderId: orderId,
      courierId: courierId,
      status: Value(status),
      version: Value(version),
    ),
  );
  return (await dao.getById(id))!;
}

void main() {
  // =========================================================================
  // DeliveryRepository — lokal Drift testlari
  // =========================================================================

  group('DeliveryRepository — lokal Drift', () {
    late AppDatabase db;
    late DeliveryRepository repository;
    late DeliveriesDao deliveriesDao;
    late OutboxDao outboxDao;

    setUp(() {
      db = _makeDb();
      repository = DeliveryRepository(db: db);
      deliveriesDao = DeliveriesDao(db);
      outboxDao = OutboxDao(db);
    });
    tearDown(() => db.close());

    // -----------------------------------------------------------------------
    // DeliveryListScreen — lokal Drift'dan ko'rsatish
    // -----------------------------------------------------------------------

    test(
      'watchAll — bo\'sh DB da bo\'sh ro\'yxat qaytaradi',
      () async {
        final stream = repository.watchAll();
        await expectLater(stream, emits(isEmpty));
      },
    );

    test(
      'watchAll — upsert dan keyin yetkazish ko\'rinadi',
      () async {
        await _insertDelivery(deliveriesDao);

        final deliveries = await repository.watchAll().first;
        expect(deliveries.length, equals(1));
        expect(deliveries.first.id, equals('delivery-001'));
        expect(deliveries.first.status, equals('assigned'));
      },
    );

    test(
      'watchAll — bir nechta yetkazish, barcha holatlar ko\'rinadi',
      () async {
        await _insertDelivery(deliveriesDao, id: 'd1');
        await _insertDelivery(deliveriesDao, id: 'd2', status: 'started');
        await _insertDelivery(deliveriesDao, id: 'd3', status: 'delivering');
        await _insertDelivery(deliveriesDao, id: 'd4', status: 'delivered');
        await _insertDelivery(deliveriesDao, id: 'd5', status: 'failed');

        final deliveries = await repository.watchAll().first;
        expect(deliveries.length, equals(5));
        final statuses = deliveries.map((d) => d.status).toSet();
        expect(
          statuses,
          containsAll(['assigned', 'started', 'delivering', 'delivered', 'failed']),
        );
      },
    );

    test(
      'watchActive — terminal holatlar (delivered/failed) ko\'rinmaydi',
      () async {
        await _insertDelivery(deliveriesDao, id: 'd1');
        await _insertDelivery(deliveriesDao, id: 'd2', status: 'started');
        await _insertDelivery(deliveriesDao, id: 'd3', status: 'delivered');
        await _insertDelivery(deliveriesDao, id: 'd4', status: 'failed');

        final active = await repository.watchActive().first;
        expect(active.length, equals(2));
        expect(active.map((d) => d.status).toList(), everyElement(
          isNot(anyOf('delivered', 'failed')),
        ));
      },
    );

    test(
      'countActive — terminal bo\'lmagan yetkazishlar soni',
      () async {
        await _insertDelivery(deliveriesDao, id: 'd1');
        await _insertDelivery(deliveriesDao, id: 'd2', status: 'started');
        await _insertDelivery(deliveriesDao, id: 'd3', status: 'delivered');

        final count = await repository.countActive();
        expect(count, equals(2));
      },
    );

    // -----------------------------------------------------------------------
    // Holat mashinasi — qonuniy o'tishlar
    // -----------------------------------------------------------------------

    test(
      'updateStatus — assigned → started: qonuniy o\'tish',
      () async {
        await _insertDelivery(deliveriesDao);

        final updated = await repository.updateStatus(
          id: 'delivery-001',
          newStatus: 'started',
        );

        expect(updated.status, equals('started'));
        expect(updated.syncStatus, equals('pending'));
      },
    );

    test(
      'updateStatus — started → delivering: qonuniy o\'tish',
      () async {
        await _insertDelivery(deliveriesDao, status: 'started', version: 2);

        final updated = await repository.updateStatus(
          id: 'delivery-001',
          newStatus: 'delivering',
        );

        expect(updated.status, equals('delivering'));
        expect(updated.version, equals(3)); // version oshdi
      },
    );

    test(
      'updateStatus — delivering → delivered: qonuniy o\'tish',
      () async {
        await _insertDelivery(deliveriesDao, status: 'delivering', version: 3);

        final updated = await repository.updateStatus(
          id: 'delivery-001',
          newStatus: 'delivered',
        );

        expect(updated.status, equals('delivered'));
      },
    );

    test(
      'updateStatus — assigned → failed: qonuniy o\'tish (istalgan holatdan)',
      () async {
        await _insertDelivery(deliveriesDao);

        final updated = await repository.updateStatus(
          id: 'delivery-001',
          newStatus: 'failed',
          failureReason: 'Mijoz uyda yo\'q edi',
        );

        expect(updated.status, equals('failed'));
      },
    );

    test(
      'updateStatus — started → failed: qonuniy o\'tish',
      () async {
        await _insertDelivery(deliveriesDao, status: 'started');

        final updated = await repository.updateStatus(
          id: 'delivery-001',
          newStatus: 'failed',
        );

        expect(updated.status, equals('failed'));
      },
    );

    // -----------------------------------------------------------------------
    // Holat mashinasi — noqonuniy o'tishlar
    // -----------------------------------------------------------------------

    test(
      'updateStatus — assigned → delivering: noqonuniy o\'tish → xato',
      () async {
        await _insertDelivery(deliveriesDao);

        await expectLater(
          () => repository.updateStatus(
            id: 'delivery-001',
            newStatus: 'delivering',
          ),
          throwsA(isA<InvalidTransitionException>()),
        );
      },
    );

    test(
      'updateStatus — assigned → delivered: noqonuniy o\'tish → xato',
      () async {
        await _insertDelivery(deliveriesDao);

        await expectLater(
          () => repository.updateStatus(
            id: 'delivery-001',
            newStatus: 'delivered',
          ),
          throwsA(isA<InvalidTransitionException>()),
        );
      },
    );

    test(
      'updateStatus — delivered → started: terminal holatdan o\'tish mumkin emas',
      () async {
        await _insertDelivery(deliveriesDao, status: 'delivered');

        await expectLater(
          () => repository.updateStatus(
            id: 'delivery-001',
            newStatus: 'started',
          ),
          throwsA(isA<InvalidTransitionException>()),
        );
      },
    );

    test(
      'updateStatus — failed → delivering: terminal holatdan o\'tish mumkin emas',
      () async {
        await _insertDelivery(deliveriesDao, status: 'failed');

        await expectLater(
          () => repository.updateStatus(
            id: 'delivery-001',
            newStatus: 'delivering',
          ),
          throwsA(isA<InvalidTransitionException>()),
        );
      },
    );

    test(
      'updateStatus — yetkazish topilmasa → DeliveryNotFoundException',
      () async {
        await expectLater(
          () => repository.updateStatus(
            id: 'non-existent-id',
            newStatus: 'started',
          ),
          throwsA(isA<DeliveryNotFoundException>()),
        );
      },
    );

    // -----------------------------------------------------------------------
    // Outbox — holat yangilaganda yoziladi
    // -----------------------------------------------------------------------

    test(
      'updateStatus — outbox da delivery.status_update yoziladi',
      () async {
        await _insertDelivery(deliveriesDao);

        await repository.updateStatus(
          id: 'delivery-001',
          newStatus: 'started',
          gpsPosition: const GpsPosition(lat: 41.2995, lng: 69.2401),
        );

        final pending = await outboxDao.getPending();
        expect(pending.length, equals(1));
        expect(pending.first.opType, equals('delivery.status_update'));

        final payload =
            jsonDecode(pending.first.payload) as Map<String, dynamic>;
        expect(payload['delivery_id'], equals('delivery-001'));
        expect(payload['status'], equals('started'));
        expect(payload['version'], equals(1));
        expect(payload['gps_lat'], isNotEmpty);
        expect(payload['gps_lng'], isNotEmpty);
      },
    );

    test(
      'updateStatus GPS yo\'q bo\'lsa — outbox payload da GPS maydon yo\'q',
      () async {
        await _insertDelivery(deliveriesDao);

        await repository.updateStatus(
          id: 'delivery-001',
          newStatus: 'started',
          // gpsPosition null
        );

        final pending = await outboxDao.getPending();
        final payload =
            jsonDecode(pending.first.payload) as Map<String, dynamic>;
        expect(payload.containsKey('gps_lat'), isFalse);
        expect(payload.containsKey('gps_lng'), isFalse);
      },
    );

    test(
      'updateStatus failed — failureReason outbox payloadda mavjud',
      () async {
        await _insertDelivery(deliveriesDao, status: 'started');

        await repository.updateStatus(
          id: 'delivery-001',
          newStatus: 'failed',
          failureReason: 'Adres noto\'g\'ri',
        );

        final pending = await outboxDao.getPending();
        final payload =
            jsonDecode(pending.first.payload) as Map<String, dynamic>;
        expect(payload['failure_reason'], equals('Adres noto\'g\'ri'));
      },
    );
  });

  // =========================================================================
  // GPS ingest — yetkazish faol holatda
  // =========================================================================

  group('DeliveryRepository — GPS ingest', () {
    late AppDatabase db;
    late DeliveryRepository repository;
    late DeliveriesDao deliveriesDao;
    late OutboxDao outboxDao;

    setUp(() {
      db = _makeDb();
      repository = DeliveryRepository(db: db);
      deliveriesDao = DeliveriesDao(db);
      outboxDao = OutboxDao(db);
    });
    tearDown(() => db.close());

    const testPos = GpsPosition(lat: 41.2995, lng: 69.2401);

    test(
      'ingestGps — started holatda delivery_id bilan outbox\'ga yoziladi',
      () async {
        await _insertDelivery(deliveriesDao, status: 'started');

        await repository.ingestGps(
          deliveryId: 'delivery-001',
          position: testPos,
        );

        final pending = await outboxDao.getPending();
        expect(pending.length, equals(1));
        expect(pending.first.opType, equals('gps.ingest'));

        final payload =
            jsonDecode(pending.first.payload) as Map<String, dynamic>;
        final points = payload['points'] as List<dynamic>;
        expect(points.length, equals(1));
        final point = points.first as Map<String, dynamic>;
        expect(point['delivery_id'], equals('delivery-001'));
        expect(point['lat'], isNotEmpty);
        expect(point['lng'], isNotEmpty);
      },
    );

    test(
      'ingestGps — delivering holatda ham yoziladi',
      () async {
        await _insertDelivery(deliveriesDao, status: 'delivering');

        await repository.ingestGps(
          deliveryId: 'delivery-001',
          position: testPos,
        );

        final pending = await outboxDao.getPending();
        expect(pending.where((p) => p.opType == 'gps.ingest').length,
            equals(1));
      },
    );

    test(
      'ingestGps — delivered (terminal) holatda — yozilmaydi (GPS to\'xtaydi)',
      () async {
        await _insertDelivery(deliveriesDao, status: 'delivered');

        await repository.ingestGps(
          deliveryId: 'delivery-001',
          position: testPos,
        );

        final pending = await outboxDao.getPending();
        expect(pending.where((p) => p.opType == 'gps.ingest'), isEmpty);
      },
    );

    test(
      'ingestGps — failed (terminal) holatda — yozilmaydi',
      () async {
        await _insertDelivery(deliveriesDao, status: 'failed');

        await repository.ingestGps(
          deliveryId: 'delivery-001',
          position: testPos,
        );

        final pending = await outboxDao.getPending();
        expect(pending.where((p) => p.opType == 'gps.ingest'), isEmpty);
      },
    );

    test(
      'ingestGps — assigned holatda — yozilmaydi (GPS faqat started/delivering)',
      () async {
        await _insertDelivery(deliveriesDao);

        await repository.ingestGps(
          deliveryId: 'delivery-001',
          position: testPos,
        );

        final pending = await outboxDao.getPending();
        expect(pending.where((p) => p.opType == 'gps.ingest'), isEmpty);
      },
    );

    test(
      'ingestGps — yetkazish topilmasa — xato ko\'tarilmaydi (silent)',
      () async {
        // Hech qanday yetkazish yo'q
        await expectLater(
          () => repository.ingestGps(
            deliveryId: 'non-existent',
            position: testPos,
          ),
          returnsNormally,
        );
      },
    );
  });

  // =========================================================================
  // Holat mashinasi birlik testlari
  // =========================================================================

  group('isValidTransition', () {
    test('assigned → started: ruxsat etilgan', () {
      expect(isValidTransition('assigned', 'started'), isTrue);
    });
    test('assigned → failed: ruxsat etilgan', () {
      expect(isValidTransition('assigned', 'failed'), isTrue);
    });
    test('assigned → delivering: ruxsat etilmagan', () {
      expect(isValidTransition('assigned', 'delivering'), isFalse);
    });
    test('assigned → delivered: ruxsat etilmagan', () {
      expect(isValidTransition('assigned', 'delivered'), isFalse);
    });
    test('started → delivering: ruxsat etilgan', () {
      expect(isValidTransition('started', 'delivering'), isTrue);
    });
    test('started → failed: ruxsat etilgan', () {
      expect(isValidTransition('started', 'failed'), isTrue);
    });
    test('started → assigned: ruxsat etilmagan', () {
      expect(isValidTransition('started', 'assigned'), isFalse);
    });
    test('delivering → delivered: ruxsat etilgan', () {
      expect(isValidTransition('delivering', 'delivered'), isTrue);
    });
    test('delivering → failed: ruxsat etilgan', () {
      expect(isValidTransition('delivering', 'failed'), isTrue);
    });
    test('delivering → assigned: ruxsat etilmagan', () {
      expect(isValidTransition('delivering', 'assigned'), isFalse);
    });
    test('delivered → started: terminal, ruxsat etilmagan', () {
      expect(isValidTransition('delivered', 'started'), isFalse);
    });
    test('failed → delivering: terminal, ruxsat etilmagan', () {
      expect(isValidTransition('failed', 'delivering'), isFalse);
    });
  });

  // =========================================================================
  // proof_photo — uploadProofPhoto stub (ApiClient yo'q)
  // =========================================================================

  group('DeliveryRepository — uploadProofPhoto stub', () {
    late AppDatabase db;
    late DeliveryRepository repository;

    setUp(() {
      db = _makeDb();
      // apiClient=null — offline stub
      repository = DeliveryRepository(db: db);
    });
    tearDown(() => db.close());

    test(
      'uploadProofPhoto — apiClient yo\'q → StateError ko\'tariladi',
      () async {
        await expectLater(
          () => repository.uploadProofPhoto(
            id: 'delivery-001',
            imagePath: '/fake/path/photo.jpg',
          ),
          throwsA(isA<StateError>()),
        );
      },
    );
  });

  // =========================================================================
  // upsertFromServer — sync pull natijasi
  // =========================================================================

  group('DeliveryRepository — upsertFromServer', () {
    late AppDatabase db;
    late DeliveryRepository repository;

    setUp(() {
      db = _makeDb();
      repository = DeliveryRepository(db: db);
    });
    tearDown(() => db.close());

    test(
      'upsertFromServer — yangi yetkazish qo\'shiladi',
      () async {
        await repository.upsertFromServer({
          'id': 'srv-delivery-001',
          'order_id': 'order-001',
          'courier_id': 'courier-001',
          'status': 'assigned',
          'version': 1,
          'assigned_at': '2026-06-18T07:00:00.000Z',
          'created_at': '2026-06-18T07:00:00.000Z',
          'updated_at': '2026-06-18T07:00:00.000Z',
        });

        final delivery = await repository.getById('srv-delivery-001');
        expect(delivery, isNotNull);
        expect(delivery!.status, equals('assigned'));
        expect(delivery.syncStatus, equals('synced'));
      },
    );

    test(
      'upsertFromServer — mavjud yetkazish yangilanadi (upsert)',
      () async {
        await repository.upsertFromServer({
          'id': 'srv-delivery-001',
          'order_id': 'order-001',
          'courier_id': 'courier-001',
          'status': 'assigned',
          'version': 1,
          'created_at': '2026-06-18T07:00:00.000Z',
          'updated_at': '2026-06-18T07:00:00.000Z',
        });

        // Yangilash — holat o'zgardi
        await repository.upsertFromServer({
          'id': 'srv-delivery-001',
          'order_id': 'order-001',
          'courier_id': 'courier-001',
          'status': 'started',
          'version': 2,
          'created_at': '2026-06-18T07:00:00.000Z',
          'updated_at': '2026-06-18T07:30:00.000Z',
        });

        final delivery = await repository.getById('srv-delivery-001');
        expect(delivery!.status, equals('started'));
        expect(delivery.version, equals(2));
      },
    );
  });
}
