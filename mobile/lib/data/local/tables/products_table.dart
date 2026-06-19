import 'package:drift/drift.dart';

/// Mahsulotlar jadvali — server katalogining lokal keshi.
/// Master data: faqat server yozadi, klient read-only.
class Products extends Table {
  TextColumn get id => text()();
  TextColumn get nameUz => text().named('name_uz')();
  TextColumn get nameRu => text().named('name_ru').nullable()();
  TextColumn get sku => text().nullable()();
  TextColumn get barcode => text().nullable()();
  TextColumn get mxikCode => text().named('mxik_code').nullable()();
  TextColumn get unit => text()();
  TextColumn get categoryId => text().named('category_id').nullable()();
  TextColumn get photoUrl => text().named('photo_url').nullable()();
  BoolColumn get isActive => boolean().named('is_active').withDefault(const Constant(true))();
  TextColumn get branchScope => text().named('branch_scope').nullable()();
  IntColumn get version => integer().withDefault(const Constant(1))();
  DateTimeColumn get createdAt => dateTime().named('created_at')();
  DateTimeColumn get updatedAt => dateTime().named('updated_at')();
  DateTimeColumn get deletedAt => dateTime().named('deleted_at').nullable()();

  // Lokal kesh uchun qo'shimcha ustun
  DateTimeColumn get cachedAt => dateTime().named('cached_at').withDefault(currentDateAndTime)();

  @override
  Set<Column<Object>> get primaryKey => {id};
}
