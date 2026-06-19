import 'package:drift/drift.dart';

import '../database.dart';
import '../tables/stores_table.dart';

part 'stores_dao.g.dart';

@DriftAccessor(tables: [Stores])
class StoresDao extends DatabaseAccessor<AppDatabase> with _$StoresDaoMixin {
  StoresDao(super.db);

  /// Barcha faol do'konlar
  Future<List<Store>> getAll() =>
      (select(stores)..where((s) => s.deletedAt.isNull())).get();

  /// ID bo'yicha
  Future<Store?> getById(String id) =>
      (select(stores)..where((s) => s.id.equals(id))).getSingleOrNull();

  /// Agent ID bo'yicha (agent o'z do'konlarini ko'radi)
  Future<List<Store>> getByAgentId(String agentId) => (select(stores)
        ..where((s) => s.agentId.equals(agentId))
        ..where((s) => s.deletedAt.isNull()))
      .get();

  /// Upsert — sync dan kelgan yangilanishlar
  Future<void> upsertFromSync(StoresCompanion store) =>
      into(stores).insertOnConflictUpdate(store);

  /// Batch upsert
  Future<void> upsertBatch(List<StoresCompanion> items) =>
      batch((b) => b.insertAllOnConflictUpdate(stores, items));

  /// Barcha do'konlarni kuzatish (admin uchun)
  Stream<List<Store>> watchAll() =>
      (select(stores)..where((s) => s.deletedAt.isNull())).watch();

  /// Watching stream
  Stream<List<Store>> watchByAgentId(String agentId) => (select(stores)
        ..where((s) => s.agentId.equals(agentId))
        ..where((s) => s.deletedAt.isNull()))
      .watch();
}
