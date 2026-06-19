import 'package:drift/drift.dart';

/// Narx segmentlari jadvali — server katalogining lokal keshi.
class PriceSegments extends Table {
  TextColumn get id => text()();
  TextColumn get name => text()();
  DateTimeColumn get createdAt => dateTime().named('created_at')();
  DateTimeColumn get updatedAt => dateTime().named('updated_at')();
  DateTimeColumn get cachedAt => dateTime().named('cached_at').withDefault(currentDateAndTime)();

  @override
  Set<Column<Object>> get primaryKey => {id};
}
