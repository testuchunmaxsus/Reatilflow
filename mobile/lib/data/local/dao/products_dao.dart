import 'package:drift/drift.dart';

import '../database.dart';
import '../tables/products_table.dart';

part 'products_dao.g.dart';

@DriftAccessor(tables: [Products])
class ProductsDao extends DatabaseAccessor<AppDatabase>
    with _$ProductsDaoMixin {
  ProductsDao(super.db);

  /// Barcha faol mahsulotlar
  Future<List<Product>> getAllActive() => (select(products)
        ..where((p) => p.isActive.equals(true))
        ..where((p) => p.deletedAt.isNull()))
      .get();

  /// ID bo'yicha bir mahsulot
  Future<Product?> getById(String id) => (select(products)
        ..where((p) => p.id.equals(id)))
      .getSingleOrNull();

  /// Barcode bo'yicha qidirish
  Future<Product?> getByBarcode(String barcode) => (select(products)
        ..where((p) => p.barcode.equals(barcode)))
      .getSingleOrNull();

  /// Nom yoki SKU bo'yicha qidirish
  Future<List<Product>> search(String query) => (select(products)
        ..where(
          (p) =>
              p.nameUz.like('%$query%') |
              p.nameRu.like('%$query%') |
              p.sku.like('%$query%') |
              p.barcode.like('%$query%'),
        )
        ..where((p) => p.isActive.equals(true))
        ..where((p) => p.deletedAt.isNull()))
      .get();

  /// Kategoriya bo'yicha
  Future<List<Product>> getByCategory(String categoryId) =>
      (select(products)
        ..where((p) => p.categoryId.equals(categoryId))
        ..where((p) => p.isActive.equals(true))
        ..where((p) => p.deletedAt.isNull()))
      .get();

  /// Upsert — sync dan kelgan yangilanishlar
  Future<void> upsertFromSync(ProductsCompanion product) =>
      into(products).insertOnConflictUpdate(product);

  /// Batch upsert — pull sync uchun
  Future<void> upsertBatch(List<ProductsCompanion> items) =>
      batch((b) => b.insertAllOnConflictUpdate(products, items));

  /// Watching stream (real-time UI)
  Stream<List<Product>> watchAllActive() => (select(products)
        ..where((p) => p.isActive.equals(true))
        ..where((p) => p.deletedAt.isNull()))
      .watch();
}
