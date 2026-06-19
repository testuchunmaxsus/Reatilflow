import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/local/database.dart';
import '../../data/local/database_provider.dart';
import 'order_repository.dart';

/// OrderRepository provider
final orderRepositoryProvider = Provider<OrderRepository>((ref) {
  final db = ref.watch(databaseProvider);
  return OrderRepository(db: db);
});

/// Barcha buyurtmalar stream
final ordersStreamProvider = StreamProvider<List<Order>>((ref) {
  final repository = ref.watch(orderRepositoryProvider);
  return repository.watchOrders();
});

/// Do'kon bo'yicha buyurtmalar stream
final ordersByStoreProvider =
    StreamProvider.family<List<Order>, String>((ref, storeId) {
  final repository = ref.watch(orderRepositoryProvider);
  return repository.watchOrdersByStore(storeId);
});

/// Buyurtma yaratish holati
sealed class CreateOrderState {
  const CreateOrderState();
}

class CreateOrderIdle extends CreateOrderState {
  const CreateOrderIdle();
}

class CreateOrderLoading extends CreateOrderState {
  const CreateOrderLoading();
}

class CreateOrderSuccess extends CreateOrderState {
  const CreateOrderSuccess({required this.result});

  final CreateOrderResult result;
}

class CreateOrderFailure extends CreateOrderState {
  const CreateOrderFailure({required this.error});

  final String error;
}

/// Buyurtma yaratish notifier
class CreateOrderNotifier extends StateNotifier<CreateOrderState> {
  CreateOrderNotifier(this._repository) : super(const CreateOrderIdle());

  final OrderRepository _repository;

  Future<void> createOrder({
    required String storeId,
    required String agentId,
    required List<OrderLineInput> lines,
    String mode = 'bozor',
    String currency = 'UZS',
  }) async {
    state = const CreateOrderLoading();
    try {
      final result = await _repository.createOrder(
        storeId: storeId,
        agentId: agentId,
        lines: lines,
        mode: mode,
        currency: currency,
      );
      state = CreateOrderSuccess(result: result);
    } on Exception catch (e) {
      state = CreateOrderFailure(error: e.toString());
    }
  }

  void reset() => state = const CreateOrderIdle();
}

final createOrderProvider =
    StateNotifierProvider.autoDispose<CreateOrderNotifier, CreateOrderState>(
  (ref) {
    final repository = ref.watch(orderRepositoryProvider);
    return CreateOrderNotifier(repository);
  },
);
