import 'package:drift/drift.dart';

/// Do'konlar (mijozlar) jadvali — lokal kesh.
class Stores extends Table {
  TextColumn get id => text()();
  TextColumn get name => text()();
  TextColumn get inn => text().nullable()();
  TextColumn get phone => text().nullable()();
  RealColumn get gpsLat => real().named('gps_lat').nullable()();
  RealColumn get gpsLng => real().named('gps_lng').nullable()();
  TextColumn get address => text().nullable()();
  TextColumn get segmentId => text().named('segment_id').nullable()();
  TextColumn get agentId => text().named('agent_id').nullable()();
  TextColumn get branchId => text().named('branch_id').nullable()();
  RealColumn get creditLimit => real().named('credit_limit').nullable()();
  IntColumn get version => integer().withDefault(const Constant(1))();
  DateTimeColumn get createdAt => dateTime().named('created_at')();
  DateTimeColumn get updatedAt => dateTime().named('updated_at')();
  DateTimeColumn get deletedAt => dateTime().named('deleted_at').nullable()();
  DateTimeColumn get cachedAt => dateTime().named('cached_at').withDefault(currentDateAndTime)();

  @override
  Set<Column<Object>> get primaryKey => {id};
}
