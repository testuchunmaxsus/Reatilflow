import 'dart:convert';

import 'package:drift/native.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:retail_mobile/data/local/dao/orders_dao.dart';
import 'package:retail_mobile/data/local/dao/outbox_dao.dart';
import 'package:retail_mobile/data/local/database.dart';
import 'package:retail_mobile/features/orders/order_repository.dart';

AppDatabase _makeDb() => AppDatabase.forTesting(NativeDatabase.memory());

void main() {
  group('OrderRepository — offline buyurtma yaratish', () {
    late AppDatabase db;
    late OrderRepository repository;

    setUp(() {
      db = _makeDb();
      repository = OrderRepository(db: db);
    });
    tearDown(() => db.close());

    test(
        'createOrder — lokal orders va outbox bitta tranzaksiyada yoziladi',
        () async {
      const storeId = 'store-uuid-001';
      const agentId = 'agent-uuid-001';
      const lines = [
        OrderLineInput(productId: 'product-uuid-001', qty: 3, unitPrice: 10000),
        OrderLineInput(productId: 'product-uuid-002', qty: 1, unitPrice: 25000),
      ];

      final result = await repository.createOrder(
        storeId: storeId,
        agentId: agentId,
        lines: lines,
      );

      expect(result.orderId, isNotEmpty);
      expect(result.clientUuid, isNotEmpty);

      final ordersDao = OrdersDao(db);
      final order = await ordersDao.getById(result.orderId);
      expect(order, isNotNull);
      expect(order!.storeId, equals(storeId));
      expect(order.agentId, equals(agentId));
      expect(order.clientUuid, equals(result.clientUuid));
      expect(order.syncStatus, equals('pending'));
      expect(order.status, equals('draft'));

      final orderLinesList = await ordersDao.getLinesForOrder(result.orderId);
      expect(orderLinesList.length, equals(2));

      final outboxDao = OutboxDao(db);
      final pending = await outboxDao.getPending();
      expect(pending.length, equals(1));
      expect(pending.first.opType, equals('order.create'));
      expect(pending.first.clientUuid, equals(result.clientUuid));

      final payload =
          jsonDecode(pending.first.payload) as Map<String, dynamic>;
      expect(payload['store_id'], equals(storeId));
      expect((payload['lines'] as List).length, equals(2));
    });

    test("createOrder — bo'sh lines ArgumentError ko'taradi", () async {
      expect(
        () => repository.createOrder(
          storeId: 'store-001',
          agentId: 'agent-001',
          lines: const [],
        ),
        throwsArgumentError,
      );
    });

    test('har yaratishda yangi clientUuid generatsiya qilinadi', () async {
      final r1 = await repository.createOrder(
        storeId: 'store-001',
        agentId: 'agent-001',
        lines: const [OrderLineInput(productId: 'p1', qty: 1)],
      );
      final r2 = await repository.createOrder(
        storeId: 'store-001',
        agentId: 'agent-001',
        lines: const [OrderLineInput(productId: 'p1', qty: 1)],
      );

      expect(r1.clientUuid, isNot(equals(r2.clientUuid)));
      expect(r1.orderId, isNot(equals(r2.orderId)));
    });

    test("createOrder — jami summa to'g'ri hisoblanadi", () async {
      final result = await repository.createOrder(
        storeId: 'store-001',
        agentId: 'agent-001',
        lines: const [
          OrderLineInput(productId: 'p1', qty: 2, unitPrice: 15000),
          OrderLineInput(productId: 'p2', qty: 3, unitPrice: 5000),
        ],
      );

      final ordersDao = OrdersDao(db);
      final order = await ordersDao.getById(result.orderId);
      // 2*15000 + 3*5000 = 30000 + 15000 = 45000
      expect(order!.totalAmount, equals(45000.0));
    });

    test('watchOrders stream buyurtmani real-time ko\'rsatadi', () async {
      // Stream ni oldindan boshlash
      final streamFuture = repository.watchOrders().first;

      await repository.createOrder(
        storeId: 'store-001',
        agentId: 'agent-001',
        lines: const [OrderLineInput(productId: 'p1', qty: 1)],
      );

      final orders = await streamFuture;
      expect(orders, isNotEmpty);
    });
  });
}
