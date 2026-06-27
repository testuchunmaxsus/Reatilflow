import 'dart:convert';

import 'package:drift/drift.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/local/dao/outbox_dao.dart';
import '../../data/local/database.dart';
import '../../data/local/database_provider.dart';

// ---------------------------------------------------------------------------
// Bir martalik buyurtma holati

sealed class OnetimeOrderState {
  const OnetimeOrderState();
}

class OnetimeOrderIdle extends OnetimeOrderState {
  const OnetimeOrderIdle();
}

class OnetimeOrderLoading extends OnetimeOrderState {
  const OnetimeOrderLoading();
}

class OnetimeOrderSuccess extends OnetimeOrderState {
  const OnetimeOrderSuccess({required this.clientUuid});
  final String clientUuid;
}

class OnetimeOrderFailure extends OnetimeOrderState {
  const OnetimeOrderFailure({required this.message});
  final String message;
}

/// Bir martalik buyurtma notifier — outbox `marketplace_order.create`.
///
/// Agent do'kon nomidan shartnomasiz catalog mahsulotini buyurtma qiladi.
/// Narx/supplier YUBORILMAYDI — server-avtoritar.
class OnetimeOrderNotifier extends StateNotifier<OnetimeOrderState> {
  OnetimeOrderNotifier(this._outboxDao) : super(const OnetimeOrderIdle());

  final OutboxDao _outboxDao;

  /// Bir martalik buyurtmani outbox'ga qo'shadi.
  ///
  /// [storeId] — do'kon UUID (majburiy, agent nomidan).
  /// [clientUuid] — idempotentlik UUID (caller generatsiya qiladi).
  /// [isOnetime] — har doim true (agent konteksti).
  Future<void> placeOrder({
    required String productId,
    required double qty,
    required String storeId,
    required String clientUuid,
  }) async {
    state = const OnetimeOrderLoading();
    try {
      final payload = <String, dynamic>{
        'client_uuid': clientUuid,
        'product_id': productId,
        'qty': qty,
        'store_id': storeId,
        'is_onetime': true,
        // Narx/supplier YUBORILMAYDI — server-avtoritar
      };

      await _outboxDao.insertOp(
        OutboxQueueCompanion.insert(
          opType: 'marketplace_order.create',
          clientUuid: clientUuid,
          payload: jsonEncode(payload),
          createdAt: Value(DateTime.now()),
        ),
      );

      state = OnetimeOrderSuccess(clientUuid: clientUuid);
    } on Exception catch (e) {
      state = OnetimeOrderFailure(message: e.toString());
    }
  }

  void reset() => state = const OnetimeOrderIdle();
}

final onetimeOrderProvider = StateNotifierProvider.autoDispose.family<
    OnetimeOrderNotifier, OnetimeOrderState, String>(
  (ref, storeId) {
    final db = ref.watch(databaseProvider);
    return OnetimeOrderNotifier(OutboxDao(db));
  },
);
