import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:retail_mobile/features/marketplace/marketplace_models.dart';
import 'package:retail_mobile/features/marketplace/marketplace_providers.dart';
import 'package:retail_mobile/features/marketplace/marketplace_repository.dart';

// ---------------------------------------------------------------------------
// Mock

class MockMarketplaceRepository extends Mock
    implements MarketplaceRepository {}

// Mocktail fallback'lar
class _FakeCreateOrderRequest extends Fake
    implements CreateMarketplaceOrderRequest {}

class _FakeAcceptOrderRequest extends Fake implements AcceptOrderRequest {}

// ---------------------------------------------------------------------------
// Yordamchi

MarketplaceBanner _makeBanner({String id = 'b-1'}) => MarketplaceBanner(
      id: id,
      imageUrl: 'https://img.com/$id.jpg',
      title: 'Banner $id',
    );

MarketplacePromo _makePromo({String id = 'p-1'}) => MarketplacePromo(
      id: id,
      productId: 'prod-$id',
      productName: 'Mahsulot $id',
      supplierName: 'Supplier $id',
      originalPrice: 10000,
      promoPrice: 8000,
      discountPercent: 20,
    );

MarketplaceProduct _makeProduct({
  String id = 'prod-001',
  String name = 'Sut',
  String supplierId = 'ent-1',
  String supplierName = 'Dairy LLC',
  double price = 5000,
}) =>
    MarketplaceProduct(
      id: id,
      name: name,
      sku: '$id-SKU',
      unit: 'litr',
      price: price,
      supplierEnterpriseId: supplierId,
      supplierEnterpriseName: supplierName,
    );

MarketplaceOrder _makeOrder({
  String id = 'order-001',
  MarketplaceOrderStatus status = MarketplaceOrderStatus.pending,
  List<MarketplaceOrderLine>? lines,
}) =>
    MarketplaceOrder(
      id: id,
      status: status,
      supplierEnterpriseId: 'ent-1',
      supplierEnterpriseName: 'Supplier LLC',
      lines: lines ?? [],
      createdAt: DateTime.now(),
    );

// ---------------------------------------------------------------------------

void main() {
  setUpAll(() {
    registerFallbackValue(_FakeCreateOrderRequest());
    registerFallbackValue(_FakeAcceptOrderRequest());
  });

  // ---------------------------------------------------------------------------
  // BannersNotifier
  // ---------------------------------------------------------------------------

  group('BannersNotifier — GET /marketplace/banners', () {
    late MockMarketplaceRepository mockRepo;
    late ProviderContainer container;

    setUp(() {
      mockRepo = MockMarketplaceRepository();
      container = ProviderContainer(
        overrides: [
          marketplaceRepositoryProvider.overrideWithValue(mockRepo),
        ],
      );
    });
    tearDown(() => container.dispose());

    test('bannerlar muvaffaqiyatli yuklanadi — BannersLoaded', () async {
      final banners = [_makeBanner(), _makeBanner(id: 'b-2')];
      when(() => mockRepo.getBanners()).thenAnswer((_) async => banners);

      await container.read(bannersNotifierProvider.notifier).load();

      final state = container.read(bannersNotifierProvider);
      expect(state, isA<BannersLoaded>());
      expect((state as BannersLoaded).banners.length, equals(2));
    });

    test('xatolikda BannersError holati', () async {
      when(() => mockRepo.getBanners())
          .thenThrow(Exception('Network error'));

      await container.read(bannersNotifierProvider.notifier).load();

      final state = container.read(bannersNotifierProvider);
      expect(state, isA<BannersError>());
    });

    test('bo\'sh banner ro\'yxati — BannersLoaded empty', () async {
      when(() => mockRepo.getBanners())
          .thenAnswer((_) async => <MarketplaceBanner>[]);

      await container.read(bannersNotifierProvider.notifier).load();

      final state = container.read(bannersNotifierProvider);
      expect(state, isA<BannersLoaded>());
      expect((state as BannersLoaded).banners, isEmpty);
    });
  });

  // ---------------------------------------------------------------------------
  // PromosNotifier
  // ---------------------------------------------------------------------------

  group('PromosNotifier — GET /marketplace/promos', () {
    late MockMarketplaceRepository mockRepo;
    late ProviderContainer container;

    setUp(() {
      mockRepo = MockMarketplaceRepository();
      container = ProviderContainer(
        overrides: [
          marketplaceRepositoryProvider.overrideWithValue(mockRepo),
        ],
      );
    });
    tearDown(() => container.dispose());

    test('promos muvaffaqiyatli yuklanadi — PromosLoaded', () async {
      final promos = [_makePromo(), _makePromo(id: 'p-2')];
      when(() => mockRepo.getPromos()).thenAnswer((_) async => promos);

      await container.read(promosNotifierProvider.notifier).load();

      final state = container.read(promosNotifierProvider);
      expect(state, isA<PromosLoaded>());
      expect((state as PromosLoaded).promos.length, equals(2));
    });

    test('promos xatolikda PromosError holati', () async {
      when(() => mockRepo.getPromos())
          .thenThrow(Exception('Server 500'));

      await container.read(promosNotifierProvider.notifier).load();

      final state = container.read(promosNotifierProvider);
      expect(state, isA<PromosError>());
    });
  });

  // ---------------------------------------------------------------------------
  // ProductsNotifier
  // ---------------------------------------------------------------------------

  group('ProductsNotifier — GET /marketplace/products', () {
    late MockMarketplaceRepository mockRepo;
    late ProviderContainer container;

    setUp(() {
      mockRepo = MockMarketplaceRepository();
      container = ProviderContainer(
        overrides: [
          marketplaceRepositoryProvider.overrideWithValue(mockRepo),
        ],
      );
    });
    tearDown(() => container.dispose());

    test('mahsulotlar yuklanadi — ProductsLoaded', () async {
      final products = [
        _makeProduct(id: 'p1'),
        _makeProduct(id: 'p2', name: 'Yogurt'),
        _makeProduct(id: 'p3', name: 'Kefir'),
      ];
      when(() => mockRepo.getProducts(
            search: any(named: 'search'),
            supplierEnterpriseId: any(named: 'supplierEnterpriseId'),
          )).thenAnswer((_) async => products);

      await container
          .read(productsNotifierProvider.notifier)
          .load();

      final state = container.read(productsNotifierProvider);
      expect(state, isA<ProductsLoaded>());
      expect((state as ProductsLoaded).products.length, equals(3));
    });

    test('xatolikda ProductsError holati', () async {
      when(() => mockRepo.getProducts(
            search: any(named: 'search'),
            supplierEnterpriseId: any(named: 'supplierEnterpriseId'),
          )).thenThrow(Exception('Timeout'));

      await container
          .read(productsNotifierProvider.notifier)
          .load();

      final state = container.read(productsNotifierProvider);
      expect(state, isA<ProductsError>());
    });
  });

  // ---------------------------------------------------------------------------
  // MarketplaceCartNotifier
  // ---------------------------------------------------------------------------

  group('MarketplaceCartNotifier — savat boshqaruvi', () {
    late ProviderContainer container;

    setUp(() {
      container = ProviderContainer();
    });
    tearDown(() => container.dispose());

    test('boshlang\'ich holat — savat bo\'sh', () {
      final state = container.read(marketplaceCartProvider);
      expect(state.items, isEmpty);
      expect(state.isEmpty, isTrue);
    });

    test('addItem — mahsulot qo\'shiladi', () {
      final product = _makeProduct();
      container.read(marketplaceCartProvider.notifier).addItem(product);

      final state = container.read(marketplaceCartProvider);
      expect(state.items.length, equals(1));
      expect(state.items.first.product.id, equals('prod-001'));
      expect(state.items.first.qty, equals(1));
    });

    test('addItem — bir xil mahsulot qayta qo\'shilsa qty oshadi', () {
      final product = _makeProduct();
      container.read(marketplaceCartProvider.notifier).addItem(product);
      container.read(marketplaceCartProvider.notifier).addItem(product);
      container.read(marketplaceCartProvider.notifier).addItem(product);

      final state = container.read(marketplaceCartProvider);
      expect(state.items.length, equals(1));
      expect(state.items.first.qty, equals(3));
    });

    test('addItem — turli mahsulotlar alohida qatorlar', () {
      final p1 = _makeProduct(id: 'p1');
      final p2 = _makeProduct(id: 'p2', name: 'Yogurt');
      container.read(marketplaceCartProvider.notifier).addItem(p1);
      container.read(marketplaceCartProvider.notifier).addItem(p2);

      final state = container.read(marketplaceCartProvider);
      expect(state.items.length, equals(2));
    });

    test('removeItem — mahsulot o\'chiriladi', () {
      final product = _makeProduct();
      container.read(marketplaceCartProvider.notifier).addItem(product);
      container
          .read(marketplaceCartProvider.notifier)
          .removeItem('prod-001');

      final state = container.read(marketplaceCartProvider);
      expect(state.items, isEmpty);
    });

    test('updateQty — miqdor yangilanadi', () {
      final product = _makeProduct();
      container.read(marketplaceCartProvider.notifier).addItem(product);
      container
          .read(marketplaceCartProvider.notifier)
          .updateQty('prod-001', 7);

      final state = container.read(marketplaceCartProvider);
      expect(state.items.first.qty, equals(7));
    });

    test('updateQty — miqdor 0 bo\'lsa o\'chiriladi', () {
      final product = _makeProduct();
      container.read(marketplaceCartProvider.notifier).addItem(product);
      container
          .read(marketplaceCartProvider.notifier)
          .updateQty('prod-001', 0);

      final state = container.read(marketplaceCartProvider);
      expect(state.items, isEmpty);
    });

    test('clear — savat tozalanadi', () {
      final p1 = _makeProduct(id: 'p1');
      final p2 = _makeProduct(id: 'p2');
      container.read(marketplaceCartProvider.notifier).addItem(p1);
      container.read(marketplaceCartProvider.notifier).addItem(p2);
      container.read(marketplaceCartProvider.notifier).clear();

      final state = container.read(marketplaceCartProvider);
      expect(state.items, isEmpty);
    });

    test('estimatedTotal — taxminiy narx hisoblanadi', () {
      final p1 = _makeProduct(id: 'p1'); // default price = 5000
      final p2 = _makeProduct(id: 'p2', price: 10000);
      container.read(marketplaceCartProvider.notifier).addItem(p1);
      container.read(marketplaceCartProvider.notifier).addItem(p1);
      container.read(marketplaceCartProvider.notifier).addItem(p2);

      final state = container.read(marketplaceCartProvider);
      // p1: qty=2 * 5000 = 10000; p2: qty=1 * 10000 = 10000; jami = 20000
      expect(state.estimatedTotal, equals(20000));
    });
  });

  // ---------------------------------------------------------------------------
  // CreateMarketplaceOrderNotifier
  // ---------------------------------------------------------------------------

  group('CreateMarketplaceOrderNotifier — POST /marketplace/orders', () {
    late MockMarketplaceRepository mockRepo;
    late ProviderContainer container;

    setUp(() {
      mockRepo = MockMarketplaceRepository();
      container = ProviderContainer(
        overrides: [
          marketplaceRepositoryProvider.overrideWithValue(mockRepo),
        ],
      );
    });
    tearDown(() => container.dispose());

    test('buyurtma muvaffaqiyatli yaratildi — CreateOrderSuccess', () async {
      final order = _makeOrder(id: 'order-new');
      when(() => mockRepo.createOrder(any()))
          .thenAnswer((_) async => order);

      await container
          .read(createMarketplaceOrderProvider.notifier)
          .createOrder(productId: 'prod-001', qty: 5);

      final state = container.read(createMarketplaceOrderProvider);
      expect(state, isA<CreateOrderSuccess>());
      expect(
          (state as CreateOrderSuccess).order.id, equals('order-new'));
    });

    test('buyurtmada faqat product_id + qty yuboriladi (narx yo\'q)',
        () async {
      CreateMarketplaceOrderRequest? capturedRequest;
      when(() => mockRepo.createOrder(any())).thenAnswer((inv) async {
        capturedRequest =
            inv.positionalArguments.first as CreateMarketplaceOrderRequest;
        return _makeOrder();
      });

      await container
          .read(createMarketplaceOrderProvider.notifier)
          .createOrder(productId: 'prod-x', qty: 3);

      expect(capturedRequest, isNotNull);
      final json = capturedRequest!.toJson();
      expect(json['product_id'], equals('prod-x'));
      expect(json['qty'], equals(3.0));
      // Narx maydonlari YO'Q
      expect(json.containsKey('price'), isFalse);
      expect(json.containsKey('unit_price'), isFalse);
      expect(json.length, equals(2));
    });

    test('xatolikda CreateOrderFailure holati', () async {
      when(() => mockRepo.createOrder(any()))
          .thenThrow(Exception('Server 500'));

      await container
          .read(createMarketplaceOrderProvider.notifier)
          .createOrder(productId: 'prod-001', qty: 1);

      final state = container.read(createMarketplaceOrderProvider);
      expect(state, isA<CreateOrderFailure>());
    });

    test('reset — idle holatga qaytadi', () async {
      when(() => mockRepo.createOrder(any()))
          .thenAnswer((_) async => _makeOrder());

      await container
          .read(createMarketplaceOrderProvider.notifier)
          .createOrder(productId: 'p', qty: 1);

      expect(container.read(createMarketplaceOrderProvider),
          isA<CreateOrderSuccess>());

      container
          .read(createMarketplaceOrderProvider.notifier)
          .reset();
      expect(container.read(createMarketplaceOrderProvider),
          isA<CreateOrderIdle>());
    });
  });

  // ---------------------------------------------------------------------------
  // OutgoingOrdersNotifier
  // ---------------------------------------------------------------------------

  group('OutgoingOrdersNotifier — GET /marketplace/orders/outgoing', () {
    late MockMarketplaceRepository mockRepo;
    late ProviderContainer container;

    setUp(() {
      mockRepo = MockMarketplaceRepository();
      container = ProviderContainer(
        overrides: [
          marketplaceRepositoryProvider.overrideWithValue(mockRepo),
        ],
      );
    });
    tearDown(() => container.dispose());

    test('buyurtmalar yuklanadi — OutgoingOrdersLoaded', () async {
      final orders = [
        _makeOrder(id: 'o-1'), // default status = pending
        _makeOrder(id: 'o-2', status: MarketplaceOrderStatus.delivered),
        _makeOrder(id: 'o-3', status: MarketplaceOrderStatus.accepted),
      ];
      when(() => mockRepo.getOutgoingOrders())
          .thenAnswer((_) async => orders);

      await container.read(outgoingOrdersProvider.notifier).load();

      final state = container.read(outgoingOrdersProvider);
      expect(state, isA<OutgoingOrdersLoaded>());
      final loaded = state as OutgoingOrdersLoaded;
      expect(loaded.orders.length, equals(3));
    });

    test('delivered holat — canAccept true', () async {
      final orders = [
        _makeOrder(id: 'o-1', status: MarketplaceOrderStatus.delivered),
      ];
      when(() => mockRepo.getOutgoingOrders())
          .thenAnswer((_) async => orders);

      await container.read(outgoingOrdersProvider.notifier).load();

      final state =
          container.read(outgoingOrdersProvider) as OutgoingOrdersLoaded;
      expect(state.orders.first.canAccept, isTrue);
    });

    test('xatolikda OutgoingOrdersError holati', () async {
      when(() => mockRepo.getOutgoingOrders())
          .thenThrow(Exception('Offline'));

      await container.read(outgoingOrdersProvider.notifier).load();

      final state = container.read(outgoingOrdersProvider);
      expect(state, isA<OutgoingOrdersError>());
    });
  });

  // ---------------------------------------------------------------------------
  // AcceptOrderNotifier
  // ---------------------------------------------------------------------------

  group('AcceptOrderNotifier — PATCH /marketplace/orders/{id}/accept', () {
    late MockMarketplaceRepository mockRepo;
    late ProviderContainer container;
    const orderId = 'order-accept-1';

    setUp(() {
      mockRepo = MockMarketplaceRepository();
      container = ProviderContainer(
        overrides: [
          marketplaceRepositoryProvider.overrideWithValue(mockRepo),
        ],
      );
    });
    tearDown(() => container.dispose());

    test('qabul qilish muvaffaqiyatli — AcceptOrderSuccess', () async {
      final acceptedOrder = _makeOrder(
        id: orderId,
        status: MarketplaceOrderStatus.accepted,
      );
      when(() => mockRepo.acceptOrder(
                orderId: any(named: 'orderId'),
                request: any(named: 'request'),
              ))
          .thenAnswer((_) async => acceptedOrder);

      final lines = [
        AcceptOrderLine(
          lineId: 'line-1',
          expiryDate: DateTime(2027, 3, 20),
          markupPercent: 10.0,
        ),
      ];

      await container
          .read(acceptOrderProvider(orderId).notifier)
          .accept(orderId: orderId, lines: lines);

      final state = container.read(acceptOrderProvider(orderId));
      expect(state, isA<AcceptOrderSuccess>());
      final success = state as AcceptOrderSuccess;
      expect(success.order.status,
          equals(MarketplaceOrderStatus.accepted));
    });

    test('qabul qilishda expiry_date + markup_percent yuboriladi', () async {
      AcceptOrderRequest? capturedRequest;
      when(() => mockRepo.acceptOrder(
                orderId: any(named: 'orderId'),
                request: any(named: 'request'),
              ))
          .thenAnswer((inv) async {
        capturedRequest =
            inv.namedArguments[const Symbol('request')] as AcceptOrderRequest;
        return _makeOrder(
            id: 'order-x', status: MarketplaceOrderStatus.accepted);
      });

      final expiryDate = DateTime(2027, 6, 15);
      final lines = [
        AcceptOrderLine(
          lineId: 'line-x',
          expiryDate: expiryDate,
          markupPercent: 25.0,
        ),
      ];

      await container
          .read(acceptOrderProvider(orderId).notifier)
          .accept(orderId: orderId, lines: lines);

      expect(capturedRequest, isNotNull);
      final json = capturedRequest!.toJson();
      final linesList = json['lines'] as List<dynamic>;
      expect(linesList.length, equals(1));
      final lineJson = linesList.first as Map<String, dynamic>;
      expect(lineJson['line_id'], equals('line-x'));
      expect(lineJson['expiry_date'], equals('2027-06-15'));
      expect(lineJson['markup_percent'], equals(25.0));
    });

    test('xatolikda AcceptOrderFailure holati', () async {
      when(() => mockRepo.acceptOrder(
                orderId: any(named: 'orderId'),
                request: any(named: 'request'),
              ))
          .thenThrow(Exception('Server error'));

      await container
          .read(acceptOrderProvider(orderId).notifier)
          .accept(orderId: orderId, lines: []);

      final state = container.read(acceptOrderProvider(orderId));
      expect(state, isA<AcceptOrderFailure>());
    });
  });
}
