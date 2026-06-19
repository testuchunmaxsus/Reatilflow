import 'package:drift/drift.dart';

import '../database.dart';
import '../tables/orders_table.dart';

part 'orders_dao.g.dart';

@DriftAccessor(tables: [Orders, OrderLines])
class OrdersDao extends DatabaseAccessor<AppDatabase> with _$OrdersDaoMixin {
  OrdersDao(super.db);

  // ---- Orders ----

  /// Barcha buyurtmalar (o'chirilmaganlar)
  Future<List<Order>> getAll() =>
      (select(orders)..where((o) => o.deletedAt.isNull())).get();

  /// ID bo'yicha
  Future<Order?> getById(String id) =>
      (select(orders)..where((o) => o.id.equals(id))).getSingleOrNull();

  /// Do'kon bo'yicha
  Future<List<Order>> getByStoreId(String storeId) => (select(orders)
        ..where((o) => o.storeId.equals(storeId))
        ..where((o) => o.deletedAt.isNull())
        ..orderBy([(o) => OrderingTerm.desc(o.createdAt)]))
      .get();

  /// Yuborilmagan (pending) buyurtmalar
  Future<List<Order>> getPending() => (select(orders)
        ..where((o) => o.syncStatus.equals('pending')))
      .get();

  /// Buyurtma yaratish (lokal tranzaksiyaning bir qismi)
  Future<void> insertOrder(OrdersCompanion order) =>
      into(orders).insert(order);

  /// Buyurtma yangilash
  Future<void> updateOrder(OrdersCompanion order) =>
      into(orders).insertOnConflictUpdate(order);

  /// Sync status yangilash
  Future<void> updateSyncStatus(
    String id, {
    required String status,
    String? serverId,
  }) async {
    await (update(orders)..where((o) => o.id.equals(id))).write(
      OrdersCompanion(
        syncStatus: Value(status),
        serverId: serverId != null ? Value(serverId) : const Value.absent(),
        updatedAt: Value(DateTime.now()),
      ),
    );
  }

  /// Watching stream — real-time UI
  Stream<List<Order>> watchAll() =>
      (select(orders)..where((o) => o.deletedAt.isNull())).watch();

  Stream<List<Order>> watchByStoreId(String storeId) => (select(orders)
        ..where((o) => o.storeId.equals(storeId))
        ..where((o) => o.deletedAt.isNull())
        ..orderBy([(o) => OrderingTerm.desc(o.createdAt)]))
      .watch();

  // ---- OrderLines ----

  /// Buyurtma qatorlari
  Future<List<OrderLine>> getLinesForOrder(String orderId) =>
      (select(orderLines)..where((l) => l.orderId.equals(orderId))).get();

  /// Qator yaratish
  Future<void> insertLine(OrderLinesCompanion line) =>
      into(orderLines).insert(line);

  /// Batch qatorlar yaratish
  Future<void> insertLines(List<OrderLinesCompanion> lines) =>
      batch((b) => b.insertAll(orderLines, lines));
}
