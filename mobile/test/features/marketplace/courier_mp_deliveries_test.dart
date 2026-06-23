// V2C: Kuryer marketplace yetkazish provider testlari.
//
// Qamrov:
//   1. CourierDeliveriesNotifier — GET /marketplace/orders/deliveries
//   2. MarketplaceDeliverNotifier — POST /marketplace/orders/{id}/proof-photo
//   3. MarketplaceOrder.canDeliver — delivering holat belgisi
//   4. MarketplaceOrder.courierId — JSON parsing

import 'dart:io';

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

// File mock (dart:io File abstract sinfi uchun)
class _FakeFile extends Fake implements File {
  @override
  String get path => '/tmp/fake_proof.jpg';
}

// ---------------------------------------------------------------------------
// Yordamchi

MarketplaceOrder _makeDelivering({
  String id = 'order-del-1',
  String courierId = 'courier-abc',
}) =>
    MarketplaceOrder(
      id: id,
      status: MarketplaceOrderStatus.delivering,
      supplierEnterpriseId: 'ent-b',
      supplierEnterpriseName: 'Supplier B',
      lines: const [],
      createdAt: DateTime.now(),
      courierId: courierId,
      totalAmount: 50000,
    );

MarketplaceOrder _makeDelivered({String id = 'order-del-1'}) =>
    MarketplaceOrder(
      id: id,
      status: MarketplaceOrderStatus.delivered,
      supplierEnterpriseId: 'ent-b',
      supplierEnterpriseName: 'Supplier B',
      lines: const [],
      createdAt: DateTime.now(),
      deliveredAt: DateTime.now(),
      proofPhotoUrl: 'https://storage.example.com/proof.jpg',
    );

// ---------------------------------------------------------------------------

void main() {
  setUpAll(() {
    registerFallbackValue(_FakeFile());
  });

  // ---------------------------------------------------------------------------
  // CourierDeliveriesNotifier
  // ---------------------------------------------------------------------------

  group('CourierDeliveriesNotifier — GET /marketplace/orders/deliveries', () {
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

    test('yetkazishlar yuklanadi — CourierDeliveriesLoaded', () async {
      final orders = [
        _makeDelivering(id: 'o-1'),
        _makeDelivering(id: 'o-2', courierId: 'courier-xyz'),
      ];
      when(() => mockRepo.getMarketplaceDeliveries())
          .thenAnswer((_) async => orders);

      await container.read(courierDeliveriesProvider.notifier).load();

      final state = container.read(courierDeliveriesProvider);
      expect(state, isA<CourierDeliveriesLoaded>());
      final loaded = state as CourierDeliveriesLoaded;
      expect(loaded.orders.length, equals(2));
    });

    test('bo\'sh ro\'yxat — CourierDeliveriesLoaded empty', () async {
      when(() => mockRepo.getMarketplaceDeliveries())
          .thenAnswer((_) async => <MarketplaceOrder>[]);

      await container.read(courierDeliveriesProvider.notifier).load();

      final state = container.read(courierDeliveriesProvider);
      expect(state, isA<CourierDeliveriesLoaded>());
      expect((state as CourierDeliveriesLoaded).orders, isEmpty);
    });

    test('xatolikda CourierDeliveriesError holati', () async {
      when(() => mockRepo.getMarketplaceDeliveries())
          .thenThrow(Exception('Network error'));

      await container.read(courierDeliveriesProvider.notifier).load();

      final state = container.read(courierDeliveriesProvider);
      expect(state, isA<CourierDeliveriesError>());
      expect(
        (state as CourierDeliveriesError).message,
        contains('Network error'),
      );
    });

    test('barcha buyurtmalar delivering holatda', () async {
      final orders = [
        _makeDelivering(id: 'o-1'),
        _makeDelivering(id: 'o-2'),
      ];
      when(() => mockRepo.getMarketplaceDeliveries())
          .thenAnswer((_) async => orders);

      await container.read(courierDeliveriesProvider.notifier).load();

      final state =
          container.read(courierDeliveriesProvider) as CourierDeliveriesLoaded;
      for (final o in state.orders) {
        expect(o.status, equals(MarketplaceOrderStatus.delivering));
        expect(o.canDeliver, isTrue);
      }
    });

    test('load qayta chaqirilsa holat yangilanadi', () async {
      // Birinchi load
      when(() => mockRepo.getMarketplaceDeliveries())
          .thenAnswer((_) async => [_makeDelivering(id: 'o-1')]);
      await container.read(courierDeliveriesProvider.notifier).load();

      final state1 = container.read(courierDeliveriesProvider);
      expect(state1, isA<CourierDeliveriesLoaded>());
      expect((state1 as CourierDeliveriesLoaded).orders.length, equals(1));

      // Ikkinchi load — yangi ro'yxat
      when(() => mockRepo.getMarketplaceDeliveries())
          .thenAnswer((_) async => [
                _makeDelivering(id: 'o-2'),
                _makeDelivering(id: 'o-3'),
              ]);
      await container.read(courierDeliveriesProvider.notifier).load();

      final state2 = container.read(courierDeliveriesProvider);
      expect(state2, isA<CourierDeliveriesLoaded>());
      expect((state2 as CourierDeliveriesLoaded).orders.length, equals(2));
    });
  });

  // ---------------------------------------------------------------------------
  // MarketplaceDeliverNotifier
  // ---------------------------------------------------------------------------

  group('MarketplaceDeliverNotifier — POST /marketplace/orders/{id}/proof-photo',
      () {
    const orderId = 'order-proof-1';
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

    test('proof yuklash muvaffaqiyatli — MarketplaceDeliverSuccess', () async {
      final delivered = _makeDelivered(id: orderId);
      when(() => mockRepo.uploadProofAndDeliver(
                orderId: any(named: 'orderId'),
                imageFile: any(named: 'imageFile'),
              ))
          .thenAnswer((_) async => delivered);

      await container
          .read(marketplaceDeliverProvider(orderId).notifier)
          .deliver(orderId: orderId, imageFile: _FakeFile());

      final state = container.read(marketplaceDeliverProvider(orderId));
      expect(state, isA<MarketplaceDeliverSuccess>());
      final success = state as MarketplaceDeliverSuccess;
      expect(success.order.status, equals(MarketplaceOrderStatus.delivered));
      expect(success.order.proofPhotoUrl, isNotNull);
    });

    test('proof yuklashda xatolik — MarketplaceDeliverFailure', () async {
      when(() => mockRepo.uploadProofAndDeliver(
                orderId: any(named: 'orderId'),
                imageFile: any(named: 'imageFile'),
              ))
          .thenThrow(Exception('403 Forbidden'));

      await container
          .read(marketplaceDeliverProvider(orderId).notifier)
          .deliver(orderId: orderId, imageFile: _FakeFile());

      final state = container.read(marketplaceDeliverProvider(orderId));
      expect(state, isA<MarketplaceDeliverFailure>());
      expect(
        (state as MarketplaceDeliverFailure).message,
        contains('403'),
      );
    });

    test('reset — idle holatga qaytadi', () async {
      final delivered = _makeDelivered(id: orderId);
      when(() => mockRepo.uploadProofAndDeliver(
                orderId: any(named: 'orderId'),
                imageFile: any(named: 'imageFile'),
              ))
          .thenAnswer((_) async => delivered);

      await container
          .read(marketplaceDeliverProvider(orderId).notifier)
          .deliver(orderId: orderId, imageFile: _FakeFile());

      expect(
        container.read(marketplaceDeliverProvider(orderId)),
        isA<MarketplaceDeliverSuccess>(),
      );

      container.read(marketplaceDeliverProvider(orderId).notifier).reset();

      expect(
        container.read(marketplaceDeliverProvider(orderId)),
        isA<MarketplaceDeliverIdle>(),
      );
    });

    test('orderId to\'g\'ri uzatiladi', () async {
      String? capturedOrderId;
      when(() => mockRepo.uploadProofAndDeliver(
                orderId: any(named: 'orderId'),
                imageFile: any(named: 'imageFile'),
              ))
          .thenAnswer((inv) async {
        capturedOrderId =
            inv.namedArguments[const Symbol('orderId')] as String;
        return _makeDelivered(id: 'order-proof-1');
      });

      await container
          .read(marketplaceDeliverProvider(orderId).notifier)
          .deliver(orderId: orderId, imageFile: _FakeFile());

      expect(capturedOrderId, equals(orderId));
    });
  });

  // ---------------------------------------------------------------------------
  // MarketplaceOrder model — V2C maydonlar
  // ---------------------------------------------------------------------------

  group('MarketplaceOrder — V2C maydonlar', () {
    test('canDeliver — delivering holatda true', () {
      final order = _makeDelivering();
      expect(order.canDeliver, isTrue);
    });

    test('canDeliver — boshqa holatlarda false', () {
      final statuses = [
        MarketplaceOrderStatus.pending,
        MarketplaceOrderStatus.confirmed,
        MarketplaceOrderStatus.delivered,
        MarketplaceOrderStatus.accepted,
        MarketplaceOrderStatus.cancelled,
      ];
      for (final status in statuses) {
        final order = MarketplaceOrder(
          id: 'o',
          status: status,
          supplierEnterpriseId: 'e',
          supplierEnterpriseName: 'S',
          lines: const [],
          createdAt: DateTime.now(),
        );
        expect(order.canDeliver, isFalse,
            reason: '$status uchun canDeliver false bo\'lishi kerak');
      }
    });

    test('fromJson — courierId parsing', () {
      final json = {
        'id': 'order-abc',
        'status': 'delivering',
        'supplier_enterprise_id': 'ent-b',
        'supplier_enterprise_name': 'Supplier B',
        'lines': <dynamic>[],
        'created_at': DateTime.now().toIso8601String(),
        'courier_id': 'courier-xyz',
        'buyer_enterprise_id': 'ent-a',
        'buyer_store_id': 'store-1',
      };

      final order = MarketplaceOrder.fromJson(json);
      expect(order.courierId, equals('courier-xyz'));
      expect(order.buyerEnterpriseId, equals('ent-a'));
      expect(order.buyerStoreId, equals('store-1'));
      expect(order.canDeliver, isTrue);
    });

    test('fromJson — courier_id null bo\'lsa null qaytadi', () {
      final json = {
        'id': 'order-abc',
        'status': 'confirmed',
        'supplier_enterprise_id': 'ent-b',
        'supplier_enterprise_name': 'Supplier B',
        'lines': <dynamic>[],
        'created_at': DateTime.now().toIso8601String(),
        // courier_id yo'q
      };

      final order = MarketplaceOrder.fromJson(json);
      expect(order.courierId, isNull);
      expect(order.canDeliver, isFalse);
    });

    test('toJson — courierId mavjud bo\'lsa chiqariladi', () {
      final order = _makeDelivering(courierId: 'courier-test');
      final json = order.toJson();
      expect(json['courier_id'], equals('courier-test'));
    });

    test('toJson — courierId null bo\'lsa chiqarilmaydi', () {
      final order = MarketplaceOrder(
        id: 'o',
        status: MarketplaceOrderStatus.pending,
        supplierEnterpriseId: 'e',
        supplierEnterpriseName: 'S',
        lines: const [],
        createdAt: DateTime.now(),
      );
      final json = order.toJson();
      expect(json.containsKey('courier_id'), isFalse);
    });
  });
}
