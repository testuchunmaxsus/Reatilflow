import 'package:drift/drift.dart';

/// Yetkazishlar jadvali — kuryerga tayinlangan yetkazishlar.
///
/// Backend /delivery scope'idan sync pull orqali keladi.
/// Holat mashinasi server-avtoritar (DELIVERY.md):
///   assigned → started → delivering → delivered (terminal)
///                      ↘ failed (terminal, istalgan non-terminal holatdan)
class Deliveries extends Table {
  /// Yetkazish UUID (server ID)
  TextColumn get id => text()();

  /// Bog'liq buyurtma UUID
  TextColumn get orderId => text().named('order_id')();

  /// Kuryer UUID
  TextColumn get courierId => text().named('courier_id')();

  /// Holat: assigned | started | delivering | delivered | failed
  TextColumn get status => text().withDefault(const Constant('assigned'))();

  /// Manzil yoki izoh (buyurtmadan tortiladi, ixtiyoriy)
  TextColumn get address => text().nullable()();

  /// Mijoz nomi (ixtiyoriy)
  TextColumn get customerName => text().named('customer_name').nullable()();

  /// Tayinlangan vaqt
  DateTimeColumn get assignedAt =>
      dateTime().named('assigned_at').nullable()();

  /// Yo'lga chiqqan vaqt
  DateTimeColumn get startedAt => dateTime().named('started_at').nullable()();

  /// Yetkazib berilgan vaqt
  DateTimeColumn get deliveredAt =>
      dateTime().named('delivered_at').nullable()();

  /// Muvaffaqiyatsizlik sababi
  TextColumn get failureReason =>
      text().named('failure_reason').nullable()();

  /// Dalil rasmi URL (serverdan keladi)
  TextColumn get proofPhotoUrl =>
      text().named('proof_photo_url').nullable()();

  /// Optimistik lock versiyasi (DELIVERY.md)
  IntColumn get version => integer().withDefault(const Constant(1))();

  /// Idempotentlik UUID (holat yangilash uchun)
  TextColumn get clientUuid => text().named('client_uuid').nullable()();

  /// Sync holati: synced | pending | conflict | error
  TextColumn get syncStatus =>
      text().named('sync_status').withDefault(const Constant('synced'))();

  DateTimeColumn get createdAt =>
      dateTime().named('created_at').withDefault(currentDateAndTime)();
  DateTimeColumn get updatedAt =>
      dateTime().named('updated_at').withDefault(currentDateAndTime)();

  @override
  Set<Column<Object>> get primaryKey => {id};
}
