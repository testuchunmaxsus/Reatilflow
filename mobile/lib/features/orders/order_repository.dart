import 'dart:convert';

import 'package:drift/drift.dart';
import 'package:uuid/uuid.dart';

import '../../data/local/dao/orders_dao.dart';
import '../../data/local/dao/outbox_dao.dart';
import '../../data/local/database.dart';

/// Offline buyurtma yaratish natijasi
class CreateOrderResult {
  const CreateOrderResult({required this.orderId, required this.clientUuid});
  final String orderId;
  final String clientUuid;
}

/// Buyurtma qatori (lokal yaratish uchun)
class OrderLineInput {
  const OrderLineInput({
    required this.productId,
    required this.qty,
    this.unitPrice = 0.0,
  });

  final String productId;
  final double qty;

  /// Lokal keshdan olingan narx (offline ko'rsatish uchun)
  final double unitPrice;
}

/// Offline-first buyurtma repository.
///
/// createOrder() BITTA TRANZAKSIYA ichida:
///   1. orders jadvali ga yozadi
///   2. order_lines jadvali ga yozadi
///   3. outbox_queue ga 'order.create' op yozadi
///
/// UI darhol natijani ko'radi — tarmoqqa bog'liq EMAS.
/// SyncService keyinchalik outbox dan serverga yuboradi.
class OrderRepository {
  OrderRepository({required AppDatabase db})
      : _db = db,
        _ordersDao = OrdersDao(db),
        _outboxDao = OutboxDao(db);

  final AppDatabase _db;
  final OrdersDao _ordersDao;
  final OutboxDao _outboxDao;

  static const Uuid _uuid = Uuid();

  /// Offline buyurtma yaratish — ATOMIK TRANZAKSIYA.
  ///
  /// [storeId] — do'kon UUID (lokal keshdan)
  /// [agentId] — joriy foydalanuvchi ID
  /// [lines]   — buyurtma qatorlari
  /// [mode]    — 'bozor' | 'oddiy'
  Future<CreateOrderResult> createOrder({
    required String storeId,
    required String agentId,
    required List<OrderLineInput> lines,
    String mode = 'bozor',
    String currency = 'UZS',
  }) async {
    if (lines.isEmpty) {
      throw ArgumentError('Buyurtma qatorlari bo\'sh bo\'lmasligi kerak');
    }

    final orderId = _uuid.v4();
    final clientUuid = _uuid.v4();
    final now = DateTime.now();

    // Jami summa (lokal narxlar bo'yicha — faqat ko'rsatish uchun)
    final totalAmount = lines.fold<double>(
      0,
      (sum, l) => sum + l.qty * l.unitPrice,
    );

    // BITTA TRANZAKSIYA
    await _db.transaction(() async {
      // 1. Buyurtma yozuvi
      await _ordersDao.insertOrder(
        OrdersCompanion.insert(
          id: orderId,
          storeId: storeId,
          agentId: Value(agentId),
          mode: Value(mode),
          status: const Value('draft'),
          totalAmount: Value(totalAmount),
          currency: Value(currency),
          orderedAt: now,
          clientUuid: clientUuid,
          createdAt: now,
          updatedAt: now,
          syncStatus: const Value('pending'),
        ),
      );

      // 2. Buyurtma qatorlari
      for (final line in lines) {
        final lineId = _uuid.v4();
        final lineTotal = line.qty * line.unitPrice;
        await _ordersDao.insertLine(
          OrderLinesCompanion.insert(
            id: lineId,
            orderId: orderId,
            productId: line.productId,
            qty: line.qty,
            unitPrice: Value(line.unitPrice),
            lineTotal: Value(lineTotal),
          ),
        );
      }

      // 3. Outbox — server kutgan 'order.create' formatda
      final payload = {
        'store_id': storeId,
        'mode': mode,
        'currency': currency,
        'lines': lines
            .map(
              (l) => {
                'product_id': l.productId,
                'qty': l.qty.toString(),
              },
            )
            .toList(),
      };

      await _outboxDao.insertOp(
        OutboxQueueCompanion.insert(
          opType: 'order.create',
          clientUuid: clientUuid,
          payload: jsonEncode(payload),
          createdAt: Value(now),
        ),
      );
    });

    return CreateOrderResult(orderId: orderId, clientUuid: clientUuid);
  }

  /// Buyurtmalar ro'yxati (lokal)
  Future<List<Order>> getOrders() => _ordersDao.getAll();

  /// Do'kon bo'yicha buyurtmalar
  Future<List<Order>> getOrdersByStore(String storeId) =>
      _ordersDao.getByStoreId(storeId);

  /// Buyurtma qatorlari
  Future<List<OrderLine>> getOrderLines(String orderId) =>
      _ordersDao.getLinesForOrder(orderId);

  /// Real-time stream
  Stream<List<Order>> watchOrders() => _ordersDao.watchAll();

  Stream<List<Order>> watchOrdersByStore(String storeId) =>
      _ordersDao.watchByStoreId(storeId);
}
