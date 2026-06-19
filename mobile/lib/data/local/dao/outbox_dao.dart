import 'package:drift/drift.dart';

import '../database.dart';
import '../tables/outbox_table.dart';

part 'outbox_dao.g.dart';

@DriftAccessor(tables: [OutboxQueue])
class OutboxDao extends DatabaseAccessor<AppDatabase> with _$OutboxDaoMixin {
  OutboxDao(super.db);

  /// Yuborilishi kerak bo'lgan op'lar (pending)
  Future<List<OutboxQueueData>> getPending() => (select(outboxQueue)
        ..where((o) => o.status.equals('pending'))
        ..orderBy([(o) => OrderingTerm.asc(o.createdAt)]))
      .get();

  /// Yangi op qo'shish
  Future<int> insertOp(OutboxQueueCompanion op) =>
      into(outboxQueue).insert(op);

  /// Status yangilash (server javobi bo'yicha)
  Future<void> updateStatus(
    int id, {
    required String status,
    String? responseData,
  }) async {
    await (update(outboxQueue)..where((o) => o.id.equals(id))).write(
      OutboxQueueCompanion(
        status: Value(status),
        lastAttemptAt: Value(DateTime.now()),
        attempts: Value(
          (await (select(outboxQueue)..where((o) => o.id.equals(id)))
                  .getSingleOrNull())
              ?.attempts ??
              0 + 1,
        ),
        responseData:
            responseData != null ? Value(responseData) : const Value.absent(),
      ),
    );
  }

  /// Urinishlar sonini oshirish
  Future<void> incrementAttempts(int id) async {
    final existing = await (select(outboxQueue)..where((o) => o.id.equals(id)))
        .getSingleOrNull();
    if (existing == null) return;
    await (update(outboxQueue)..where((o) => o.id.equals(id))).write(
      OutboxQueueCompanion(
        attempts: Value(existing.attempts + 1),
        lastAttemptAt: Value(DateTime.now()),
      ),
    );
  }

  /// Muvaffaqiyatli yuborilgan op'larni o'chirish
  Future<void> deleteApplied() async {
    await (delete(outboxQueue)
          ..where(
            (o) => o.status.isIn(['applied', 'duplicate']),
          ))
        .go();
  }

  /// client_uuid bo'yicha mavjudligini tekshirish
  Future<OutboxQueueData?> getByClientUuid(String clientUuid) =>
      (select(outboxQueue)..where((o) => o.clientUuid.equals(clientUuid)))
          .getSingleOrNull();

  /// Pending op'lar soni (badge uchun)
  Stream<int> watchPendingCount() {
    final query = select(outboxQueue)..where((o) => o.status.equals('pending'));
    return query.watch().map((rows) => rows.length);
  }
}
