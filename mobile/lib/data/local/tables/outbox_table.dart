import 'package:drift/drift.dart';

/// Transactional outbox jadvali.
///
/// Har offline mutatsiyada bitta tranzaksiya ichida:
///   1. Lokal o'zgarish (orders/order_lines/...) yoziladi.
///   2. Bu jadvalga yozuv qo'shiladi.
///
/// SyncService tarmoq mavjud bo'lganda batch POST /sync/push ga yuboradi.
class OutboxQueue extends Table {
  IntColumn get id => integer().autoIncrement()();

  /// Operatsiya turi: 'order.create', 'order.status_update', ...
  TextColumn get opType => text().named('op_type')();

  /// Idempotentlik UUID (klient tomonida uuid v4 generatsiya)
  TextColumn get clientUuid => text().named('client_uuid')();

  /// JSON payload (server kutgan formatda)
  TextColumn get payload => text()();

  DateTimeColumn get createdAt => dateTime().named('created_at').withDefault(currentDateAndTime)();

  /// pending | sent | applied | duplicate | conflict | error
  TextColumn get status => text().withDefault(const Constant('pending'))();

  /// Urinishlar soni (retry uchun)
  IntColumn get attempts => integer().withDefault(const Constant(0))();

  /// Oxirgi urinish vaqti
  DateTimeColumn get lastAttemptAt => dateTime().named('last_attempt_at').nullable()();

  /// Server javobi yoki xato xabari
  TextColumn get responseData => text().named('response_data').nullable()();
}
