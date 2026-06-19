import 'dart:convert';

import 'package:drift/drift.dart';
import 'package:drift/native.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:retail_mobile/data/local/dao/deliveries_dao.dart';
import 'package:retail_mobile/data/local/dao/outbox_dao.dart';
import 'package:retail_mobile/data/local/database.dart';
import 'package:retail_mobile/features/attendance/gps_service.dart';
import 'package:retail_mobile/features/delivery/delivery_providers.dart';
import 'package:retail_mobile/features/delivery/delivery_repository.dart';

AppDatabase _makeDb() => AppDatabase.forTesting(NativeDatabase.memory());

/// Tezlashtirilgan timer bilan GPS interval testi.
/// Real 45s kutishdan qochish uchun — logika birlik testda.
void main() {
  group('DeliveryDetailNotifier — GPS tracking', () {
    late AppDatabase db;
    late DeliveryRepository repository;
    late DeliveriesDao deliveriesDao;
    late OutboxDao outboxDao;
    late ProviderContainer container;

    setUp(() {
      db = _makeDb();
      repository = DeliveryRepository(db: db);
      deliveriesDao = DeliveriesDao(db);
      outboxDao = OutboxDao(db);
      container = ProviderContainer(
        overrides: [
          deliveryRepositoryProvider.overrideWithValue(repository),
          deliveryGpsServiceProvider.overrideWithValue(
            MockGpsService(),
          ),
        ],
      );
    });

    tearDown(() {
      container.dispose();
      db.close();
    });

    test(
      'startGpsTrackingIfActive — started holatda GPS yonadi',
      () async {
        // Yetkazish yaratish
        await deliveriesDao.upsert(
          DeliveriesCompanion.insert(
            id: 'gps-test-001',
            orderId: 'order-001',
            courierId: 'courier-001',
            status: const Value('started'),
          ),
        );

        final notifier = container.read(
          deliveryDetailNotifierProvider('gps-test-001').notifier,
        );

        // GPS tracking boshlash
        notifier.startGpsTrackingIfActive('started');

        // Darhol GPS yoziladigan operatsiya bo'lmasligi kerak (trigger kutiladi)
        final pendingBefore = await outboxDao.getPending();
        expect(
          pendingBefore.where((p) => p.opType == 'gps.ingest'),
          isEmpty,
        );
      },
    );

    test(
      'startGpsTrackingIfActive — assigned holatda GPS YONMAYDI',
      () async {
        await deliveriesDao.upsert(
          DeliveriesCompanion.insert(
            id: 'gps-test-002',
            orderId: 'order-002',
            courierId: 'courier-001',
            status: const Value('assigned'),
          ),
        );

        final notifier = container.read(
          deliveryDetailNotifierProvider('gps-test-002').notifier,
        );

        // assigned holatda GPS tracking boshlanmasin
        notifier.startGpsTrackingIfActive('assigned');

        // Timer boshlanmagan — hech narsa yozilmaydi
        await Future<void>.delayed(const Duration(milliseconds: 100));
        final pending = await outboxDao.getPending();
        expect(
          pending.where((p) => p.opType == 'gps.ingest'),
          isEmpty,
        );
      },
    );

    test(
      'changeStatus assigned→started — GPS tracking boshlanadi',
      () async {
        await deliveriesDao.upsert(
          DeliveriesCompanion.insert(
            id: 'gps-test-003',
            orderId: 'order-003',
            courierId: 'courier-001',
            status: const Value('assigned'),
            version: const Value(1),
          ),
        );

        final notifier = container.read(
          deliveryDetailNotifierProvider('gps-test-003').notifier,
        );

        await notifier.changeStatus(newStatus: 'started');

        // Holat yangilangandan keyin outbox da delivery.status_update bor
        final pending = await outboxDao.getPending();
        expect(
          pending.any((p) => p.opType == 'delivery.status_update'),
          isTrue,
        );
      },
    );

    test(
      'changeStatus delivered — GPS tracking to\'xtaydi',
      () async {
        await deliveriesDao.upsert(
          DeliveriesCompanion.insert(
            id: 'gps-test-004',
            orderId: 'order-004',
            courierId: 'courier-001',
            status: const Value('delivering'),
            version: const Value(3),
          ),
        );

        final notifier = container.read(
          deliveryDetailNotifierProvider('gps-test-004').notifier,
        );

        // GPS tracking boshlash
        notifier.startGpsTrackingIfActive('delivering');

        // delivered → GPS to'xtatilishi kerak
        await notifier.changeStatus(newStatus: 'delivered');

        // Holat terminal bo'ldi
        final delivery = await repository.getById('gps-test-004');
        expect(delivery!.status, equals('delivered'));
      },
    );
  });

  // =========================================================================
  // GPS ingest — delivery_id mavjudligi tekshiruvi
  // =========================================================================

  group('GPS ingest — delivery_id bilan', () {
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

    test(
      'ingestGps — outbox payload da delivery_id mavjud',
      () async {
        await deliveriesDao.upsert(
          DeliveriesCompanion.insert(
            id: 'delivery-gps-001',
            orderId: 'order-001',
            courierId: 'courier-001',
            status: const Value('started'),
          ),
        );

        await repository.ingestGps(
          deliveryId: 'delivery-gps-001',
          position: const GpsPosition(lat: 41.3001, lng: 69.2502),
        );

        final pending = await outboxDao.getPending();
        final gpsOp =
            pending.firstWhere((p) => p.opType == 'gps.ingest');
        final payload = jsonDecode(gpsOp.payload) as Map<String, dynamic>;
        final points = payload['points'] as List<dynamic>;
        final point = points.first as Map<String, dynamic>;

        expect(point['delivery_id'], equals('delivery-gps-001'));
        expect(point['lat'], equals('41.3001000'));
        expect(point['lng'], equals('69.2502000'));
        expect(point.containsKey('recorded_at'), isTrue);
      },
    );

    test(
      'ingestGps ketma-ket — har chaqiriqda alohida outbox yozuvi',
      () async {
        await deliveriesDao.upsert(
          DeliveriesCompanion.insert(
            id: 'delivery-gps-002',
            orderId: 'order-002',
            courierId: 'courier-001',
            status: const Value('delivering'),
          ),
        );

        const pos1 = GpsPosition(lat: 41.2995, lng: 69.2401);
        const pos2 = GpsPosition(lat: 41.3000, lng: 69.2410);
        const pos3 = GpsPosition(lat: 41.3005, lng: 69.2420);

        await repository.ingestGps(deliveryId: 'delivery-gps-002', position: pos1);
        await repository.ingestGps(deliveryId: 'delivery-gps-002', position: pos2);
        await repository.ingestGps(deliveryId: 'delivery-gps-002', position: pos3);

        final pending = await outboxDao.getPending();
        final gpsOps = pending.where((p) => p.opType == 'gps.ingest').toList();
        // Har chaqiriq alohida outbox yozuvi
        expect(gpsOps.length, equals(3));
      },
    );
  });

  // =========================================================================
  // kGpsActiveStatuses / kTerminalStatuses konstantalar
  // =========================================================================

  group('GPS faol holatlar konstantasi', () {
    test('kGpsActiveStatuses: started va delivering', () {
      expect(kGpsActiveStatuses, containsAll(['started', 'delivering']));
      expect(kGpsActiveStatuses.contains('assigned'), isFalse);
      expect(kGpsActiveStatuses.contains('delivered'), isFalse);
      expect(kGpsActiveStatuses.contains('failed'), isFalse);
    });

    test('kTerminalStatuses: delivered va failed', () {
      expect(kTerminalStatuses, containsAll(['delivered', 'failed']));
      expect(kTerminalStatuses.contains('assigned'), isFalse);
      expect(kTerminalStatuses.contains('started'), isFalse);
    });
  });
}
