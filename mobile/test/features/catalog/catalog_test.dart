import 'package:drift/drift.dart' hide isNull, isNotNull;
import 'package:drift/native.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:retail_mobile/data/local/dao/products_dao.dart';
import 'package:retail_mobile/data/local/database.dart';

AppDatabase _makeDb() => AppDatabase.forTesting(NativeDatabase.memory());

void main() {
  group('ProductsDao — lokal katalog', () {
    late AppDatabase db;
    late ProductsDao dao;

    setUp(() {
      db = _makeDb();
      dao = ProductsDao(db);
    });
    tearDown(() => db.close());

    Future<void> insertProduct({
      required String id,
      required String nameUz,
      String? sku,
      String? barcode,
      String unit = 'dona',
      bool isActive = true,
    }) async {
      await dao.upsertFromSync(
        ProductsCompanion.insert(
          id: id,
          nameUz: nameUz,
          unit: unit,
          sku: Value(sku),
          barcode: Value(barcode),
          isActive: Value(isActive),
          createdAt: DateTime.now(),
          updatedAt: DateTime.now(),
        ),
      );
    }

    test('mahsulot qo\'shiladi va getAllActive da ko\'rinadi', () async {
      await insertProduct(id: 'p1', nameUz: 'Non oq');
      final all = await dao.getAllActive();
      expect(all.length, equals(1));
      expect(all.first.nameUz, equals('Non oq'));
    });

    test('faol bo\'lmagan mahsulot getAllActive da ko\'rinmaydi', () async {
      await insertProduct(id: 'p1', nameUz: 'Faol mahsulot');
      await insertProduct(id: 'p2', nameUz: 'Nofaol mahsulot', isActive: false);

      final active = await dao.getAllActive();
      expect(active.length, equals(1));
      expect(active.first.id, equals('p1'));
    });

    test('getById — mavjud mahsulot qaytaradi', () async {
      await insertProduct(id: 'prod-001', nameUz: 'Limon');
      final product = await dao.getById('prod-001');
      expect(product, isNotNull);
      expect(product!.nameUz, equals('Limon'));
    });

    test('getById — yo\'q ID uchun null qaytaradi', () async {
      final product = await dao.getById('non-existent');
      expect(product, isNull);
    });

    test('getByBarcode — barcode bo\'yicha topadi', () async {
      await insertProduct(
          id: 'p1', nameUz: 'Sharbat', barcode: '4600001234567');
      final product = await dao.getByBarcode('4600001234567');
      expect(product, isNotNull);
      expect(product!.nameUz, equals('Sharbat'));
    });

    test('search — nom bo\'yicha qidiradi', () async {
      await insertProduct(id: 'p1', nameUz: 'Non oq');
      await insertProduct(id: 'p2', nameUz: 'Non to\'q');
      await insertProduct(id: 'p3', nameUz: 'Limon');

      final results = await dao.search('non');
      expect(results.length, equals(2));
      expect(results.every((p) => p.nameUz.toLowerCase().contains('non')),
          isTrue);
    });

    test('search — SKU bo\'yicha qidiradi', () async {
      await insertProduct(id: 'p1', nameUz: 'Mahsulot', sku: 'BREAD-001');
      final results = await dao.search('BREAD');
      expect(results.length, equals(1));
    });

    test('search — barcode bo\'yicha qidiradi', () async {
      await insertProduct(
          id: 'p1', nameUz: 'Mahsulot', barcode: '4601234567890');
      final results = await dao.search('4601234567');
      expect(results.length, equals(1));
    });

    test('search — natija topilmasa bo\'sh list qaytaradi', () async {
      await insertProduct(id: 'p1', nameUz: 'Non');
      final results = await dao.search('mavjud_emas_xyz_123');
      expect(results, isEmpty);
    });

    test('upsertFromSync — mavjud mahsulot yangilanadi', () async {
      await insertProduct(id: 'p1', nameUz: 'Eski nom');
      await dao.upsertFromSync(
        ProductsCompanion.insert(
          id: 'p1',
          nameUz: 'Yangi nom',
          unit: 'kg',
          createdAt: DateTime.now(),
          updatedAt: DateTime.now(),
        ),
      );

      final product = await dao.getById('p1');
      expect(product!.nameUz, equals('Yangi nom'));
    });

    test('batch upsert — ko\'p mahsulotlar birgalikda qo\'shiladi', () async {
      final companions = List.generate(
        10,
        (i) => ProductsCompanion.insert(
          id: 'product-$i',
          nameUz: 'Mahsulot $i',
          unit: 'dona',
          createdAt: DateTime.now(),
          updatedAt: DateTime.now(),
        ),
      );
      await dao.upsertBatch(companions);

      final all = await dao.getAllActive();
      expect(all.length, equals(10));
    });

    test('watchAllActive stream — mahsulot qo\'shilganda yangilanadi',
        () async {
      final stream = dao.watchAllActive();
      final first = await stream.first;
      expect(first, isEmpty);

      await insertProduct(id: 'p1', nameUz: 'Yangi mahsulot');

      final second = await stream.first;
      expect(second.length, equals(1));
    });

    test('o\'chirilgan mahsulot (deletedAt bor) getAllActive da ko\'rinmaydi',
        () async {
      await dao.upsertFromSync(
        ProductsCompanion.insert(
          id: 'p1',
          nameUz: 'O\'chirilgan mahsulot',
          unit: 'dona',
          deletedAt: Value(DateTime.now()),
          createdAt: DateTime.now(),
          updatedAt: DateTime.now(),
        ),
      );

      final all = await dao.getAllActive();
      expect(all.where((p) => p.id == 'p1'), isEmpty);
    });
  });
}
