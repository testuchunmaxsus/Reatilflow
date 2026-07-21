import 'package:drift/drift.dart';

import '../database.dart';
import '../tables/outbox_table.dart';

part 'outbox_dao.g.dart';

@DriftAccessor(tables: [OutboxQueue])
class OutboxDao extends DatabaseAccessor<AppDatabase> with _$OutboxDaoMixin {
  OutboxDao(super.db);

  /// Qayta urinish uchun ruxsat etilgan maksimal attempts soni.
  static const int _maxAttempts = 5;

  /// Yuborilishi kerak bo'lgan op'lar — pending yoki (error va attempts < max).
  /// Shu tarza xato bo'lgan op'lar keyingi sync'da qayta uriniladi (dead-letter
  /// faqat attempts limitiga yetganda).
  Future<List<OutboxQueueData>> getPending() => (select(outboxQueue)
        ..where((o) =>
            o.status.equals('pending') |
            (o.status.equals('error') &
                o.attempts.isSmallerThanValue(_maxAttempts)))
        ..orderBy([(o) => OrderingTerm.asc(o.createdAt)]))
      .get();

  /// Yangi op qo'shish
  Future<int> insertOp(OutboxQueueCompanion op) =>
      into(outboxQueue).insert(op);

  /// Status yangilash (server javobi bo'yicha).
  ///
  /// Attempts hisobi bu yerda YO'Q — yagona manba [incrementAttempts]
  /// (xato yo'lida sync_service alohida chaqiradi). Bu yerda ham oshirish
  /// ikki marta hisoblashga olib kelardi.
  Future<void> updateStatus(
    int id, {
    required String status,
    String? responseData,
  }) async {
    await (update(outboxQueue)..where((o) => o.id.equals(id))).write(
      OutboxQueueCompanion(
        status: Value(status),
        lastAttemptAt: Value(DateTime.now()),
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
