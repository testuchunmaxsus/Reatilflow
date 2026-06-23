import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:retail_mobile/features/pos/pos_models.dart';
import 'package:retail_mobile/features/pos/pos_providers.dart';
import 'package:retail_mobile/features/pos/pos_repository.dart';

// ---------------------------------------------------------------------------
// Mock

class MockPosRepository extends Mock implements PosRepository {}

/// Mocktail uchun PosSaleRequest fallback
class _FakePosSaleRequest extends Fake implements PosSaleRequest {}

// ---------------------------------------------------------------------------
// Yordamchi

InventoryItem _makeItem({
  String id = 'prod-001',
  String name = 'Sut',
  double qty = 50,
  double salePrice = 10000,
  bool isExpired = false,
  bool isNearExpiry = false,
  int? daysToExpiry,
}) =>
    InventoryItem(
      productId: id,
      productName: name,
      sku: '$id-SKU',
      unit: 'litr',
      qty: qty,
      costPrice: 8000,
      salePrice: salePrice,
      isExpired: isExpired,
      isNearExpiry: isNearExpiry,
      daysToExpiry: daysToExpiry,
    );

PosSaleResponse _makeResponse({
  String saleId = 'sale-001',
  double totalAmount = 30000,
}) =>
    PosSaleResponse(
      saleId: saleId,
      totalAmount: totalAmount,
      paymentMethod: 'cash',
      createdAt: DateTime.now(),
      items: [],
    );

// ---------------------------------------------------------------------------
// CartNotifier
// ---------------------------------------------------------------------------

void main() {
  setUpAll(() {
    registerFallbackValue(_FakePosSaleRequest());
  });

  group('CartNotifier — savat boshqaruvi', () {
    late ProviderContainer container;

    setUp(() {
      container = ProviderContainer();
    });
    tearDown(() => container.dispose());

    test('boshlang\'ich holat — savat bo\'sh', () {
      final state = container.read(cartProvider);
      expect(state.items, isEmpty);
      expect(state.paymentMethod, equals('cash'));
    });

    test('addItem — mahsulot qo\'shiladi', () {
      final item = _makeItem();
      container.read(cartProvider.notifier).addItem(item);

      final state = container.read(cartProvider);
      expect(state.items.length, equals(1));
      expect(state.items.first.item.productId, equals('prod-001'));
      expect(state.items.first.qty, equals(1));
    });

    test('addItem — bir xil mahsulot qayta qo\'shilsa qty oshadi', () {
      final item = _makeItem();
      container.read(cartProvider.notifier).addItem(item);
      container.read(cartProvider.notifier).addItem(item);
      container.read(cartProvider.notifier).addItem(item);

      final state = container.read(cartProvider);
      expect(state.items.length, equals(1));
      expect(state.items.first.qty, equals(3));
    });

    test('addItem — expired mahsulot qo\'shilmaydi (blok)', () {
      final expired = _makeItem(id: 'exp-001', isExpired: true);
      container.read(cartProvider.notifier).addItem(expired);

      final state = container.read(cartProvider);
      expect(state.items, isEmpty); // expired blok
    });

    test('addItem — near_expiry mahsulot qo\'shiladi (faqat ogohlantirish)', () {
      final nearExpiry =
          _makeItem(id: 'near-001', isNearExpiry: true, daysToExpiry: 2);
      container.read(cartProvider.notifier).addItem(nearExpiry);

      final state = container.read(cartProvider);
      expect(state.items.length, equals(1)); // near_expiry blok emas
      expect(state.items.first.item.isNearExpiry, isTrue);
    });

    test('removeItem — mahsulot savatdan o\'chiriladi', () {
      final item = _makeItem();
      container.read(cartProvider.notifier).addItem(item);
      container.read(cartProvider.notifier).removeItem('prod-001');

      final state = container.read(cartProvider);
      expect(state.items, isEmpty);
    });

    test('updateQty — miqdor yangilanadi', () {
      final item = _makeItem();
      container.read(cartProvider.notifier).addItem(item);
      container.read(cartProvider.notifier).updateQty('prod-001', 5);

      final state = container.read(cartProvider);
      expect(state.items.first.qty, equals(5));
    });

    test('updateQty — miqdor 0 yoki manfiy bo\'lsa o\'chiriladi', () {
      final item = _makeItem();
      container.read(cartProvider.notifier).addItem(item);
      container.read(cartProvider.notifier).updateQty('prod-001', 0);

      final state = container.read(cartProvider);
      expect(state.items, isEmpty);
    });

    test('setPaymentMethod — to\'lov usuli o\'zgartirish', () {
      container.read(cartProvider.notifier).setPaymentMethod('card');

      final state = container.read(cartProvider);
      expect(state.paymentMethod, equals('card'));
    });

    test('clear — savat tozalanadi', () {
      final item = _makeItem();
      container.read(cartProvider.notifier).addItem(item);
      container.read(cartProvider.notifier).clear();

      final state = container.read(cartProvider);
      expect(state.items, isEmpty);
    });

    test('estimatedTotal — taxminiy jami hisoblanadi', () {
      final item1 = _makeItem(id: 'p1'); // salePrice = 10000 (default)
      final item2 = _makeItem(id: 'p2', salePrice: 5000);
      container.read(cartProvider.notifier).addItem(item1);
      container.read(cartProvider.notifier).addItem(item1);
      container.read(cartProvider.notifier).addItem(item2);

      final state = container.read(cartProvider);
      // item1: qty=2, 2*10000 = 20000; item2: qty=1, 1*5000 = 5000; jami = 25000
      expect(state.estimatedTotal, equals(25000));
    });
  });

  // ---------------------------------------------------------------------------
  // CheckoutNotifier — mock repository bilan
  // ---------------------------------------------------------------------------

  group('CheckoutNotifier — POST /pos/sales', () {
    late MockPosRepository mockRepo;
    late ProviderContainer container;

    setUp(() {
      mockRepo = MockPosRepository();
      container = ProviderContainer(
        overrides: [
          posRepositoryProvider.overrideWithValue(mockRepo),
        ],
      );
    });
    tearDown(() => container.dispose());

    test('checkout — muvaffaqiyatli sotuv → CheckoutSuccess', () async {
      when(() => mockRepo.createSale(any()))
          .thenAnswer((_) async => _makeResponse());

      // Savatga mahsulot qo'shish
      final item = _makeItem();
      container.read(cartProvider.notifier).addItem(item);
      final cart = container.read(cartProvider);

      await container.read(checkoutProvider.notifier).checkout(cart);

      final state = container.read(checkoutProvider);
      expect(state, isA<CheckoutSuccess>());
      expect((state as CheckoutSuccess).response.saleId, equals('sale-001'));
    });

    test('checkout — 422 expired → CheckoutFailure isExpiredError=true', () async {
      when(() => mockRepo.createSale(any()))
          .thenThrow(PosProductExpiredException());

      final item = _makeItem(isNearExpiry: true); // near_expiry lekin server 422
      container.read(cartProvider.notifier).addItem(item);
      final cart = container.read(cartProvider);

      await container.read(checkoutProvider.notifier).checkout(cart);

      final state = container.read(checkoutProvider);
      expect(state, isA<CheckoutFailure>());
      expect((state as CheckoutFailure).isExpiredError, isTrue);
    });

    test('checkout — tarmoq xatosi → CheckoutFailure', () async {
      when(() => mockRepo.createSale(any()))
          .thenThrow(Exception('Network error'));

      final item = _makeItem();
      container.read(cartProvider.notifier).addItem(item);
      final cart = container.read(cartProvider);

      await container.read(checkoutProvider.notifier).checkout(cart);

      final state = container.read(checkoutProvider);
      expect(state, isA<CheckoutFailure>());
      expect((state as CheckoutFailure).isExpiredError, isFalse);
    });

    test('checkout — bo\'sh savat bilan chaqirilganda idle qoladi', () async {
      final cart = container.read(cartProvider); // bo'sh
      await container.read(checkoutProvider.notifier).checkout(cart);

      final state = container.read(checkoutProvider);
      expect(state, isA<CheckoutIdle>());
    });

    test('checkout — faqat product_id + qty yuboriladi (narx yubormaydi)',
        () async {
      PosSaleRequest? capturedRequest;
      when(() => mockRepo.createSale(any())).thenAnswer((inv) async {
        capturedRequest =
            inv.positionalArguments.first as PosSaleRequest;
        return _makeResponse();
      });

      final item = _makeItem(id: 'p1', salePrice: 99999);
      container.read(cartProvider.notifier).addItem(item);
      final cart = container.read(cartProvider);

      await container.read(checkoutProvider.notifier).checkout(cart);

      expect(capturedRequest, isNotNull);
      final json = capturedRequest!.toJson();
      final items = json['items'] as List<dynamic>;
      final first = items.first as Map<String, dynamic>;
      // Narx maydonlari YO'Q
      expect(first.containsKey('price'), isFalse);
      expect(first.containsKey('unit_price'), isFalse);
      expect(first['product_id'], equals('p1'));
    });

    test('reset — idle holatga qaytadi', () async {
      when(() => mockRepo.createSale(any()))
          .thenAnswer((_) async => _makeResponse());

      final item = _makeItem();
      container.read(cartProvider.notifier).addItem(item);
      final cart = container.read(cartProvider);
      await container.read(checkoutProvider.notifier).checkout(cart);

      // Success holatda
      expect(container.read(checkoutProvider), isA<CheckoutSuccess>());

      container.read(checkoutProvider.notifier).reset();
      expect(container.read(checkoutProvider), isA<CheckoutIdle>());
    });
  });

  // ---------------------------------------------------------------------------
  // InventoryNotifier — mock repository bilan
  // ---------------------------------------------------------------------------

  group('InventoryNotifier — GET /marketplace/inventory', () {
    late MockPosRepository mockRepo;
    late ProviderContainer container;

    setUp(() {
      mockRepo = MockPosRepository();
      container = ProviderContainer(
        overrides: [
          posRepositoryProvider.overrideWithValue(mockRepo),
        ],
      );
    });
    tearDown(() => container.dispose());

    test('yuklangandan so\'ng InventoryLoaded holati', () async {
      final items = [
        _makeItem(id: 'p1'),
        _makeItem(id: 'p2', isExpired: true),
        _makeItem(id: 'p3', isNearExpiry: true),
      ];
      when(() => mockRepo.getInventory()).thenAnswer((_) async => items);

      // Kutish uchun biraz vaqt beramiz (InventoryNotifier.load() async)
      await Future<void>.delayed(Duration.zero);

      final state = container.read(inventoryNotifierProvider);
      // Yuklash boshlangan — loading yoki loaded
      expect(state, isA<InventoryLoading>());

      // load() ni to'liq bajarilishini kutamiz
      await container
          .read(inventoryNotifierProvider.notifier)
          .load();

      final loadedState = container.read(inventoryNotifierProvider);
      expect(loadedState, isA<InventoryLoaded>());
      final loaded = loadedState as InventoryLoaded;
      expect(loaded.items.length, equals(3));
    });

    test('xatolikda InventoryError holati', () async {
      when(() => mockRepo.getInventory())
          .thenThrow(Exception('Server error'));

      await container
          .read(inventoryNotifierProvider.notifier)
          .load();

      final state = container.read(inventoryNotifierProvider);
      expect(state, isA<InventoryError>());
    });

    test('expired va near_expiry mahsulotlar to\'g\'ri belgilanadi', () async {
      final items = [
        _makeItem(id: 'p1'), // normal
        _makeItem(id: 'p2', isExpired: true), // expired
        _makeItem(id: 'p3', isNearExpiry: true, daysToExpiry: 1), // near
      ];
      when(() => mockRepo.getInventory()).thenAnswer((_) async => items);

      await container
          .read(inventoryNotifierProvider.notifier)
          .load();

      final state =
          container.read(inventoryNotifierProvider) as InventoryLoaded;
      expect(state.items.where((i) => i.isExpired).length, equals(1));
      expect(state.items.where((i) => i.isNearExpiry).length, equals(1));
      expect(
          state.items.where((i) => !i.isExpired && !i.isNearExpiry).length,
          equals(1));
    });
  });

  // ---------------------------------------------------------------------------
  // filteredInventoryProvider
  // ---------------------------------------------------------------------------

  group('filteredInventoryProvider — qidiruv filtri', () {
    late MockPosRepository mockRepo;
    late ProviderContainer container;

    setUp(() {
      mockRepo = MockPosRepository();
      container = ProviderContainer(
        overrides: [
          posRepositoryProvider.overrideWithValue(mockRepo),
        ],
      );
    });
    tearDown(() => container.dispose());

    test('qidiruvsiz — barcha mahsulotlar', () async {
      final items = [
        _makeItem(id: 'p1'),
        _makeItem(id: 'p2', name: 'Yogurt'),
        _makeItem(id: 'p3', name: 'Kefir'),
      ];
      when(() => mockRepo.getInventory()).thenAnswer((_) async => items);

      await container
          .read(inventoryNotifierProvider.notifier)
          .load();

      final filtered = container.read(filteredInventoryProvider);
      expect(filtered.length, equals(3));
    });

    test('qidiruv bo\'yicha filtrlash', () async {
      final items = [
        _makeItem(id: 'p1'),
        _makeItem(id: 'p2', name: 'Yogurt'),
        _makeItem(id: 'p3', name: 'Kefir'),
      ];
      when(() => mockRepo.getInventory()).thenAnswer((_) async => items);

      await container
          .read(inventoryNotifierProvider.notifier)
          .load();

      container
          .read(inventorySearchProvider.notifier)
          .setQuery('yogurt');

      final filtered = container.read(filteredInventoryProvider);
      expect(filtered.length, equals(1));
      expect(filtered.first.productName, equals('Yogurt'));
    });
  });
}
