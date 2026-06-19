import 'package:drift/drift.dart';

/// Buyurtmalar jadvali — lokal.
/// Offline yaratiladi, sync orqali serverga yuboriladi.
class Orders extends Table {
  /// Lokal UUID (klient tomonida uuid v4 generatsiya qilinadi).
  /// Sync bo'lganda server_id bilan yangilanadi.
  TextColumn get id => text()();
  TextColumn get storeId => text().named('store_id')();
  TextColumn get agentId => text().named('agent_id').nullable()();

  /// 'bozor' | 'oddiy'
  TextColumn get mode => text().withDefault(const Constant('bozor'))();

  /// draft | confirmed | packed | delivering | delivered | canceled
  TextColumn get status => text().withDefault(const Constant('draft'))();

  RealColumn get totalAmount => real().named('total_amount').withDefault(const Constant(0.0))();
  TextColumn get currency => text().withDefault(const Constant('UZS'))();
  DateTimeColumn get orderedAt => dateTime().named('ordered_at')();

  /// Idempotentlik uchun — har offline yaratishda uuid v4
  TextColumn get clientUuid => text().named('client_uuid')();

  TextColumn get branchId => text().named('branch_id').nullable()();
  TextColumn get warehouseId => text().named('warehouse_id').nullable()();
  IntColumn get version => integer().withDefault(const Constant(1))();

  /// Server'dan kelgan real ID (sync dan keyin to'ldiriladi)
  TextColumn get serverId => text().named('server_id').nullable()();

  DateTimeColumn get createdAt => dateTime().named('created_at')();
  DateTimeColumn get updatedAt => dateTime().named('updated_at')();
  DateTimeColumn get deletedAt => dateTime().named('deleted_at').nullable()();

  /// pending | synced | conflict | error
  TextColumn get syncStatus => text().named('sync_status').withDefault(const Constant('pending'))();

  @override
  Set<Column<Object>> get primaryKey => {id};
}

/// Buyurtma qatorlari
class OrderLines extends Table {
  TextColumn get id => text()();
  TextColumn get orderId => text().named('order_id')();
  TextColumn get productId => text().named('product_id')();
  RealColumn get qty => real()();
  RealColumn get unitPrice => real().named('unit_price').withDefault(const Constant(0.0))();
  TextColumn get segmentId => text().named('segment_id').nullable()();
  RealColumn get discount => real().withDefault(const Constant(0.0))();
  RealColumn get lineTotal => real().named('line_total').withDefault(const Constant(0.0))();

  @override
  Set<Column<Object>> get primaryKey => {id};
}
