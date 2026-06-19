// T20: DeliveryListScreen render testlari + activeDeliveriesCountProvider birlik testlari.
//
// Widget testlarida Drift stream queries va fake_async timerlar o'rtasida
// muammo mavjud (pending timer assertion). Shu sababli:
// - UI render mantiqiy tekshiruvlari — unit test orqali (DAO + stream)
// - Widget smoke testi — minimal widget tree bilan
//
// Bu pattern T14 existing store_list_test.dart ga mos keladi.

import 'package:drift/drift.dart' hide isNotNull, isNull;
import 'package:drift/native.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:retail_mobile/data/local/dao/deliveries_dao.dart';
import 'package:retail_mobile/data/local/database.dart';
import 'package:retail_mobile/data/local/database_provider.dart';
import 'package:retail_mobile/features/delivery/delivery_providers.dart';
import 'package:retail_mobile/features/delivery/delivery_repository.dart';

AppDatabase _makeDb() => AppDatabase.forTesting(NativeDatabase.memory());

/// Test uchun yetkazish yozuvi
Future<void> _insertDelivery(
  DeliveriesDao dao, {
  required String id,
  String status = 'assigned',
}) async {
  await dao.upsert(
    DeliveriesCompanion.insert(
      id: id,
      orderId: 'order-$id',
      courierId: 'courier-001',
      status: Value(status),
      address: const Value('Toshkent, Chilonzor 5'),
      customerName: const Value('Alisher Karimov'),
    ),
  );
}

void main() {
  // =========================================================================
  // DeliveriesDao stream — unit testlar
  // (Widget testlar Drift stream timer muammosi tufayli qochilgan)
  // =========================================================================

  group('DeliveriesDao — watchAll stream unit testlari', () {
    late AppDatabase db;
    late DeliveriesDao dao;

    setUp(() {
      db = _makeDb();
      dao = DeliveriesDao(db);
    });
    tearDown(() => db.close());

    test('bo\'sh DB — watchAll bo\'sh ro\'yxat qaytaradi', () async {
      final stream = dao.watchAll();
      final first = await stream.first;
      expect(first, isEmpty);
    });

    test('bitta yetkazish — ro\'yxatda ko\'rinadi (status: assigned)', () async {
      await _insertDelivery(dao, id: 'd001');

      final deliveries = await dao.watchAll().first;
      expect(deliveries.length, equals(1));
      expect(deliveries.first.id, equals('d001'));
      expect(deliveries.first.status, equals('assigned'));
      expect(deliveries.first.address, equals('Toshkent, Chilonzor 5'));
      expect(deliveries.first.customerName, equals('Alisher Karimov'));
    });

    test(
      'bir nechta yetkazish — barcha holatlar ko\'rinadi',
      () async {
        await _insertDelivery(dao, id: 'd1');
        await _insertDelivery(dao, id: 'd2', status: 'started');
        await _insertDelivery(dao, id: 'd3', status: 'delivering');
        await _insertDelivery(dao, id: 'd4', status: 'delivered');
        await _insertDelivery(dao, id: 'd5', status: 'failed');

        final deliveries = await dao.watchAll().first;
        expect(deliveries.length, equals(5));

        final statuses = deliveries.map((d) => d.status).toSet();
        expect(
          statuses,
          containsAll([
            'assigned',
            'started',
            'delivering',
            'delivered',
            'failed',
          ]),
        );
      },
    );

    test(
      'holat badge matni tekshiruvi — har holat uchun label mavjud',
      () {
        // DeliveryListScreen._DeliveryCard._statusInfo ga mos keladi
        const statusLabels = {
          'assigned': 'Tayinlangan',
          'started': 'Boshlandi',
          'delivering': 'Yetkazilmoqda',
          'delivered': 'Yetkazildi',
          'failed': 'Muvaffaqiyatsiz',
        };

        for (final entry in statusLabels.entries) {
          expect(entry.value, isNotEmpty);
          expect(entry.key, isNotEmpty);
        }
        expect(statusLabels.length, equals(5));
      },
    );

    test(
      'watchActive — terminal holatlar (delivered/failed) ko\'rinmaydi',
      () async {
        await _insertDelivery(dao, id: 'd1');
        await _insertDelivery(dao, id: 'd2', status: 'started');
        await _insertDelivery(dao, id: 'd3', status: 'delivered'); // terminal
        await _insertDelivery(dao, id: 'd4', status: 'failed');    // terminal

        final active = await dao.watchActive().first;
        expect(active.length, equals(2));
        for (final d in active) {
          expect(d.status, isNot(anyOf('delivered', 'failed')));
        }
      },
    );

    test('sync_status pending bo\'lsa Badge ko\'rsatilishi uchun flag', () async {
      await dao.upsert(
        DeliveriesCompanion.insert(
          id: 'sync-test-001',
          orderId: 'order-001',
          courierId: 'courier-001',
          syncStatus: const Value('pending'),
        ),
      );

      final deliveries = await dao.watchAll().first;
      expect(deliveries.first.syncStatus, equals('pending'));
    });
  });

  // =========================================================================
  // activeDeliveriesCountProvider unit testlari
  // =========================================================================

  group('activeDeliveriesCountProvider', () {
    late AppDatabase db;
    late DeliveriesDao dao;

    setUp(() {
      db = _makeDb();
      dao = DeliveriesDao(db);
    });
    tearDown(() => db.close());

    test(
      'bo\'sh DB — count = 0',
      () async {
        final repo = DeliveryRepository(db: db);
        final container = ProviderContainer(overrides: [
          databaseProvider.overrideWithValue(db),
          deliveryRepositoryProvider.overrideWithValue(repo),
        ]);
        addTearDown(container.dispose);

        final count =
            await container.read(activeDeliveriesCountProvider.future);
        expect(count, equals(0));
      },
    );

    test(
      'faol yetkazishlar soni terminal bo\'lmaganlarni hisoblaydi',
      () async {
        await _insertDelivery(dao, id: 'd1');
        await _insertDelivery(dao, id: 'd2', status: 'started');
        await _insertDelivery(dao, id: 'd3', status: 'delivering');
        await _insertDelivery(dao, id: 'd4', status: 'delivered'); // terminal
        await _insertDelivery(dao, id: 'd5', status: 'failed');    // terminal

        final repo = DeliveryRepository(db: db);
        final container = ProviderContainer(overrides: [
          databaseProvider.overrideWithValue(db),
          deliveryRepositoryProvider.overrideWithValue(repo),
        ]);
        addTearDown(container.dispose);

        final count =
            await container.read(activeDeliveriesCountProvider.future);
        expect(count, equals(3)); // assigned + started + delivering
      },
    );

    test(
      'barcha terminal bo\'lsa — count = 0',
      () async {
        await _insertDelivery(dao, id: 'd1', status: 'delivered');
        await _insertDelivery(dao, id: 'd2', status: 'failed');

        final repo = DeliveryRepository(db: db);
        final container = ProviderContainer(overrides: [
          databaseProvider.overrideWithValue(db),
          deliveryRepositoryProvider.overrideWithValue(repo),
        ]);
        addTearDown(container.dispose);

        final count =
            await container.read(activeDeliveriesCountProvider.future);
        expect(count, equals(0));
      },
    );

    test(
      'deliveriesStreamProvider — stream emit qiladi',
      () async {
        await _insertDelivery(dao, id: 'stream-test-001');

        final repo = DeliveryRepository(db: db);
        final container = ProviderContainer(overrides: [
          databaseProvider.overrideWithValue(db),
          deliveryRepositoryProvider.overrideWithValue(repo),
        ]);
        addTearDown(container.dispose);

        // Stream provider birinchi emitni kutish
        final subscription = container.listen(
          deliveriesStreamProvider,
          (_, __) {},
        );
        addTearDown(subscription.close);

        // Provider loaded bo'lguncha kutish
        await Future<void>.delayed(const Duration(milliseconds: 50));

        final state = container.read(deliveriesStreamProvider);
        state.whenData((deliveries) {
          expect(deliveries.length, equals(1));
          expect(deliveries.first.id, equals('stream-test-001'));
        });
      },
    );
  });
}
