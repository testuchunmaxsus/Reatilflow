import 'package:drift/drift.dart';

import '../database.dart';
import '../tables/deliveries_table.dart';

part 'deliveries_dao.g.dart';

@DriftAccessor(tables: [Deliveries])
class DeliveriesDao extends DatabaseAccessor<AppDatabase>
    with _$DeliveriesDaoMixin {
  DeliveriesDao(super.db);

  /// Barcha yetkazishlarni kuzatish (holat badge uchun)
  Stream<List<Delivery>> watchAll() =>
      (select(deliveries)
            ..orderBy([
              (d) => OrderingTerm.desc(d.assignedAt),
            ]))
          .watch();

  /// Faol yetkazishlarni olish (terminal bo'lmagan)
  Stream<List<Delivery>> watchActive() =>
      (select(deliveries)
            ..where((d) => d.status.isNotIn(['delivered', 'failed']))
            ..orderBy([(d) => OrderingTerm.desc(d.assignedAt)]))
          .watch();

  /// ID bo'yicha bitta yetkazishni kuzatish
  Stream<Delivery?> watchById(String id) =>
      (select(deliveries)..where((d) => d.id.equals(id)))
          .watchSingleOrNull();

  /// ID bo'yicha bitta yetkazishni olish
  Future<Delivery?> getById(String id) =>
      (select(deliveries)..where((d) => d.id.equals(id))).getSingleOrNull();

  /// Upsert (sync pull yoki lokal yangilash)
  Future<void> upsert(DeliveriesCompanion companion) =>
      into(deliveries).insertOnConflictUpdate(companion);

  /// Holat yangilash (lokal — outbox yuborilgandan keyin)
  Future<void> updateStatus(
    String id, {
    required String status,
    String? failureReason,
    String? proofPhotoUrl,
    int? version,
    String? syncStatus,
  }) async {
    await (update(deliveries)..where((d) => d.id.equals(id))).write(
      DeliveriesCompanion(
        status: Value(status),
        failureReason:
            failureReason != null ? Value(failureReason) : const Value.absent(),
        proofPhotoUrl:
            proofPhotoUrl != null ? Value(proofPhotoUrl) : const Value.absent(),
        version: version != null ? Value(version) : const Value.absent(),
        syncStatus:
            syncStatus != null ? Value(syncStatus) : const Value.absent(),
        updatedAt: Value(DateTime.now()),
      ),
    );
  }

  /// Jami tayinlangan (assigned+started+delivering) soni — dashboard uchun
  Future<int> countActive() async {
    final query = select(deliveries)
      ..where((d) => d.status.isNotIn(['delivered', 'failed']));
    final rows = await query.get();
    return rows.length;
  }
}
