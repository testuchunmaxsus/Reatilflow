import 'dart:io';

import 'package:drift/drift.dart';
import 'package:drift/native.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

import 'tables/deliveries_table.dart';
import 'tables/orders_table.dart';
import 'tables/outbox_table.dart';
import 'tables/price_segments_table.dart';
import 'tables/products_table.dart';
import 'tables/stores_table.dart';
import 'tables/sync_cursor_table.dart';

part 'database.g.dart';

/// RETAIL lokal SQLite bazasi (Drift ORM).
///
/// Offline-first yadro: barcha UI shu bazadan o'qiydi,
/// hech qachon to'g'ridan-to'g'ri tarmoqqa murojaat qilmaydi.
///
/// schemaVersion=2: deliveries jadvali qo'shildi (T20 kuryer ilovasi).
@DriftDatabase(
  tables: [
    Products,
    PriceSegments,
    Stores,
    Orders,
    OrderLines,
    OutboxQueue,
    SyncCursors,
    Deliveries,
  ],
)
class AppDatabase extends _$AppDatabase {
  AppDatabase() : super(_openConnection());

  /// Test uchun in-memory baza
  AppDatabase.forTesting(super.executor);

  @override
  int get schemaVersion => 2;

  /// Lokal bazani to'liq tozalaydi — logout va qurilma almashinuvi uchun.
  ///
  /// Tozalanadigan jadvallar:
  ///   products, price_segments, stores, orders, order_lines,
  ///   outbox_queue, sync_cursors, deliveries
  ///
  /// Tranzaksiyada bajariladi: qisman tozalanmaydi.
  /// DIQQAT: outbox'dagi yuborilmagan operatsiyalar yo'qoladi —
  /// bu boshqa foydalanuvchi nomidan yuborilmasligidan muhimroq.
  Future<void> clearAllData() => transaction(() async {
        await delete(products).go();
        await delete(priceSegments).go();
        await delete(stores).go();
        await delete(orderLines).go();
        await delete(orders).go();
        await delete(outboxQueue).go();
        await delete(deliveries).go();
        // sync_cursors ni tozalab, standart qatorni qayta kiriting
        // Keyingi login since=0 dan to'liq sync qiladi
        await delete(syncCursors).go();
        await into(syncCursors).insertOnConflictUpdate(
          SyncCursorsCompanion.insert(id: const Value('default')),
        );
      });

  @override
  MigrationStrategy get migration => MigrationStrategy(
        onCreate: (Migrator m) async {
          await m.createAll();
          // Standart sync kursor yozuvi
          await into(syncCursors).insertOnConflictUpdate(
            SyncCursorsCompanion.insert(id: const Value('default')),
          );
        },
        onUpgrade: (Migrator m, int from, int to) async {
          if (from < 2) {
            // T20: deliveries jadvali qo'shildi
            await m.createTable(deliveries);
          }
        },
      );
}

LazyDatabase _openConnection() {
  return LazyDatabase(() async {
    final dbFolder = await getApplicationDocumentsDirectory();
    final file = File(p.join(dbFolder.path, 'retail.sqlite'));
    return NativeDatabase.createInBackground(file);
  });
}
