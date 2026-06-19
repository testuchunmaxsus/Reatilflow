import 'package:drift/drift.dart';

/// Sync kursor jadvali — server'dan delta pull uchun.
///
/// ADR §3.5: klient o'z soatiga ishonmaydi; kursor server'dan kelgan
/// monoton seq qiymatiga asoslanadi.
///
/// Har doim bitta qator: id = 'default'.
class SyncCursors extends Table {
  /// Har doim 'default' — bitta global kursor
  TextColumn get id => text().withDefault(const Constant('default'))();

  /// GET /sync/pull?since= ga yuboriladigan qiymat.
  /// 0 = birinchi sync (boshidan).
  IntColumn get lastSeq => integer().named('last_seq').withDefault(const Constant(0))();

  DateTimeColumn get updatedAt => dateTime().named('updated_at').withDefault(currentDateAndTime)();

  @override
  Set<Column<Object>> get primaryKey => {id};
}
