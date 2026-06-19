import 'package:drift/native.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:retail_mobile/data/local/dao/outbox_dao.dart';
import 'package:retail_mobile/data/local/dao/sync_cursor_dao.dart';
import 'package:retail_mobile/data/local/database.dart';

AppDatabase _makeDb() => AppDatabase.forTesting(NativeDatabase.memory());

void main() {
  group('AppDatabase sxema', () {
    late AppDatabase db;

    setUp(() => db = _makeDb());
    tearDown(() => db.close());

    test('baza yaratiladi va sync kursor default row bor', () async {
      final cursorDao = SyncCursorDao(db);
      final seq = await cursorDao.getLastSeq();
      expect(seq, equals(0));
    });

    test('sync kursor yangilanadi', () async {
      final cursorDao = SyncCursorDao(db);
      await cursorDao.updateLastSeq(42);
      expect(await cursorDao.getLastSeq(), equals(42));

      await cursorDao.updateLastSeq(87);
      expect(await cursorDao.getLastSeq(), equals(87));
    });
  });

  group('OutboxDao', () {
    late AppDatabase db;
    late OutboxDao outboxDao;

    setUp(() {
      db = _makeDb();
      outboxDao = OutboxDao(db);
    });
    tearDown(() => db.close());

    test("op qo'shiladi va pending listda ko'rinadi", () async {
      await outboxDao.insertOp(
        OutboxQueueCompanion.insert(
          opType: 'order.create',
          clientUuid: 'test-uuid-001',
          payload: '{"store_id":"s1","lines":[]}',
        ),
      );

      final pending = await outboxDao.getPending();
      expect(pending.length, equals(1));
      expect(pending.first.opType, equals('order.create'));
      expect(pending.first.clientUuid, equals('test-uuid-001'));
      expect(pending.first.status, equals('pending'));
    });

    test('applied op delete qilinadi', () async {
      final id = await outboxDao.insertOp(
        OutboxQueueCompanion.insert(
          opType: 'order.create',
          clientUuid: 'test-uuid-002',
          payload: '{}',
        ),
      );

      await outboxDao.updateStatus(id, status: 'applied');
      await outboxDao.deleteApplied();

      final pending = await outboxDao.getPending();
      expect(pending, isEmpty);
    });

    test('conflict op pending listda qolmaydi', () async {
      final id = await outboxDao.insertOp(
        OutboxQueueCompanion.insert(
          opType: 'order.create',
          clientUuid: 'test-uuid-003',
          payload: '{}',
        ),
      );

      await outboxDao.updateStatus(id, status: 'conflict');

      final pending = await outboxDao.getPending();
      expect(pending, isEmpty);
    });

    test('attempts oshiriladi', () async {
      final id = await outboxDao.insertOp(
        OutboxQueueCompanion.insert(
          opType: 'order.create',
          clientUuid: 'test-uuid-004',
          payload: '{}',
        ),
      );

      await outboxDao.incrementAttempts(id);
      await outboxDao.incrementAttempts(id);

      final item = await outboxDao.getByClientUuid('test-uuid-004');
      expect(item?.attempts, equals(2));
    });

    test('watchPendingCount stream ishlaydi', () async {
      final stream = outboxDao.watchPendingCount();
      await expectLater(stream, emits(0));
    });
  });
}
