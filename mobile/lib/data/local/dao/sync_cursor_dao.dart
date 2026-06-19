import 'package:drift/drift.dart';

import '../database.dart';
import '../tables/sync_cursor_table.dart';

part 'sync_cursor_dao.g.dart';

@DriftAccessor(tables: [SyncCursors])
class SyncCursorDao extends DatabaseAccessor<AppDatabase>
    with _$SyncCursorDaoMixin {
  SyncCursorDao(super.db);

  static const String _defaultId = 'default';

  /// Joriy kursor qiymatini olish
  Future<int> getLastSeq() async {
    final row = await (select(syncCursors)
          ..where((c) => c.id.equals(_defaultId)))
        .getSingleOrNull();
    return row?.lastSeq ?? 0;
  }

  /// Kursor yangilash (pull muvaffaqiyatli bo'lganda)
  Future<void> updateLastSeq(int newSeq) async {
    await into(syncCursors).insertOnConflictUpdate(
      SyncCursorsCompanion.insert(
        id: const Value(_defaultId),
        lastSeq: Value(newSeq),
        updatedAt: Value(DateTime.now()),
      ),
    );
  }
}
