import 'package:drift/drift.dart' hide isNull, isNotNull;
import 'package:drift/native.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:retail_mobile/data/local/dao/stores_dao.dart';
import 'package:retail_mobile/data/local/database.dart';

AppDatabase _makeDb() => AppDatabase.forTesting(NativeDatabase.memory());

void main() {
  group('StoresDao — lokal do\'konlar', () {
    late AppDatabase db;
    late StoresDao dao;

    setUp(() {
      db = _makeDb();
      dao = StoresDao(db);
    });
    tearDown(() => db.close());

    Future<void> insertStore({
      required String id,
      required String name,
      String? agentId,
      String? address,
      double? gpsLat,
      double? gpsLng,
    }) async {
      await dao.upsertFromSync(
        StoresCompanion.insert(
          id: id,
          name: name,
          agentId: Value(agentId),
          address: Value(address),
          gpsLat: Value(gpsLat),
          gpsLng: Value(gpsLng),
          createdAt: DateTime.now(),
          updatedAt: DateTime.now(),
        ),
      );
    }

    test('do\'kon qo\'shiladi va getAll da ko\'rinadi', () async {
      await insertStore(id: 's1', name: 'Sarvar do\'koni', agentId: 'agent1');
      final all = await dao.getAll();
      expect(all.length, equals(1));
      expect(all.first.name, equals('Sarvar do\'koni'));
    });

    test('getByAgentId — agent o\'z do\'konlarini ko\'radi', () async {
      await insertStore(id: 's1', name: 'Do\'kon A', agentId: 'agent1');
      await insertStore(id: 's2', name: 'Do\'kon B', agentId: 'agent2');
      await insertStore(id: 's3', name: 'Do\'kon C', agentId: 'agent1');

      final agent1Stores = await dao.getByAgentId('agent1');
      expect(agent1Stores.length, equals(2));
      expect(agent1Stores.every((s) => s.agentId == 'agent1'), isTrue);
    });

    test('getById — ID bo\'yicha topadi', () async {
      await insertStore(id: 'store-uuid-001', name: 'Test do\'kon');
      final store = await dao.getById('store-uuid-001');
      expect(store, isNotNull);
      expect(store!.name, equals('Test do\'kon'));
    });

    test('getById — yo\'q ID uchun null qaytaradi', () async {
      final store = await dao.getById('non-existent-id');
      expect(store, isNull);
    });

    test('upsertFromSync — mavjud do\'kon yangilanadi', () async {
      await insertStore(id: 's1', name: 'Eski nom');
      await dao.upsertFromSync(
        StoresCompanion.insert(
          id: 's1',
          name: 'Yangi nom',
          createdAt: DateTime.now(),
          updatedAt: DateTime.now(),
        ),
      );

      final store = await dao.getById('s1');
      expect(store!.name, equals('Yangi nom'));
    });

    test('GPS koordinatalar saqlanadi', () async {
      await insertStore(
        id: 's1',
        name: 'GPS do\'kon',
        gpsLat: 41.2995,
        gpsLng: 69.2401,
      );

      final store = await dao.getById('s1');
      expect(store!.gpsLat, closeTo(41.2995, 0.0001));
      expect(store.gpsLng, closeTo(69.2401, 0.0001));
    });

    test('o\'chirilgan do\'kon (deletedAt bor) getAll da ko\'rinmaydi',
        () async {
      await insertStore(id: 's1', name: 'Faol do\'kon');
      // Soft-delete
      await db.into(db.stores).insertOnConflictUpdate(
            StoresCompanion.insert(
              id: 's1',
              name: 'O\'chirilgan do\'kon',
              deletedAt: Value(DateTime.now()),
              createdAt: DateTime.now(),
              updatedAt: DateTime.now(),
            ),
          );

      final all = await dao.getAll();
      expect(all.where((s) => s.id == 's1'), isEmpty);
    });

    test('batch upsert — ko\'p do\'konlar birgalikda qo\'shiladi', () async {
      final companions = List.generate(
        5,
        (i) => StoresCompanion.insert(
          id: 'store-$i',
          name: "Do'kon $i",
          createdAt: DateTime.now(),
          updatedAt: DateTime.now(),
        ),
      );
      await dao.upsertBatch(companions);

      final all = await dao.getAll();
      expect(all.length, equals(5));
    });

    test('watchAll stream — do\'kon qo\'shilganda yangilanadi', () async {
      final stream = dao.watchAll();

      // Birinchi emit — bo'sh
      final first = await stream.first;
      expect(first, isEmpty);

      await insertStore(id: 's1', name: 'Yangi do\'kon');

      // Ikkinchi emit — 1 ta do'kon
      final second = await stream.first;
      expect(second.length, equals(1));
    });
  });
}
