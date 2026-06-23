import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../auth/auth_providers.dart';
import 'pos_models.dart';
import 'pos_repository.dart';

// ---------------------------------------------------------------------------
// Repository

/// PosRepository provider.
final posRepositoryProvider = Provider<PosRepository>((ref) {
  final api = ref.watch(apiClientProvider);
  return PosRepository(apiClient: api);
});

// ---------------------------------------------------------------------------
// Inventory — mahsulotlar ro'yxati + kesh

/// Inventar yuklash holati
sealed class InventoryState {
  const InventoryState();
}

class InventoryLoading extends InventoryState {
  const InventoryLoading();
}

class InventoryLoaded extends InventoryState {
  const InventoryLoaded({required this.items});
  final List<InventoryItem> items;
}

class InventoryError extends InventoryState {
  const InventoryError({required this.message});
  final String message;
}

/// Inventar notifier — serverdan yuklaydi va lokal keshda saqlaydi.
class InventoryNotifier extends StateNotifier<InventoryState> {
  InventoryNotifier(this._repository) : super(const InventoryLoading()) {
    load();
  }

  final PosRepository _repository;

  /// Mahsulotlarni serverdan yuklash.
  Future<void> load() async {
    state = const InventoryLoading();
    try {
      final items = await _repository.getInventory();
      state = InventoryLoaded(items: items);
    } on Exception catch (e) {
      state = InventoryError(message: e.toString());
    }
  }
}

final inventoryNotifierProvider =
    StateNotifierProvider.autoDispose<InventoryNotifier, InventoryState>(
  (ref) {
    final repository = ref.watch(posRepositoryProvider);
    return InventoryNotifier(repository);
  },
);

// ---------------------------------------------------------------------------
// Qidiruv filtri

class InventorySearchNotifier extends StateNotifier<String> {
  InventorySearchNotifier() : super('');

  void setQuery(String query) => state = query;
  void clear() => state = '';
}

final inventorySearchProvider =
    StateNotifierProvider.autoDispose<InventorySearchNotifier, String>(
  (ref) => InventorySearchNotifier(),
);

/// Filtr qilingan inventar — qidiruv bo'yicha.
final filteredInventoryProvider = Provider.autoDispose<List<InventoryItem>>(
  (ref) {
    final inventoryState = ref.watch(inventoryNotifierProvider);
    final query = ref.watch(inventorySearchProvider).toLowerCase();

    if (inventoryState is! InventoryLoaded) return [];

    final items = inventoryState.items;
    if (query.isEmpty) return items;

    return items.where((item) {
      return item.productName.toLowerCase().contains(query) ||
          item.sku.toLowerCase().contains(query);
    }).toList();
  },
);

// ---------------------------------------------------------------------------
// POS sotuv (savat + checkout)

/// Savat elementi
class CartItem {
  const CartItem({required this.item, required this.qty});

  final InventoryItem item;
  final double qty;

  CartItem copyWith({InventoryItem? item, double? qty}) =>
      CartItem(item: item ?? this.item, qty: qty ?? this.qty);
}

/// Savat holati
class CartState {
  const CartState({this.items = const [], this.paymentMethod = 'cash'});

  final List<CartItem> items;
  final String paymentMethod;

  CartState copyWith({
    List<CartItem>? items,
    String? paymentMethod,
  }) =>
      CartState(
        items: items ?? this.items,
        paymentMethod: paymentMethod ?? this.paymentMethod,
      );

  /// Savatdagi jami miqdor (lokal, server hisoblagan narx emas).
  /// Faqat display uchun.
  double get estimatedTotal =>
      items.fold(0.0, (sum, e) => sum + e.item.salePrice * e.qty);
}

/// Savat notifier
class CartNotifier extends StateNotifier<CartState> {
  CartNotifier() : super(const CartState());

  /// Mahsulot qo'shish. Expired mahsulot qo'shib bo'lmaydi.
  void addItem(InventoryItem item) {
    if (item.isExpired) return; // expired — blok
    final existing = state.items.indexWhere(
      (e) => e.item.productId == item.productId,
    );
    if (existing >= 0) {
      final updated = List<CartItem>.from(state.items);
      updated[existing] =
          updated[existing].copyWith(qty: updated[existing].qty + 1);
      state = state.copyWith(items: updated);
    } else {
      state = state.copyWith(
        items: [...state.items, CartItem(item: item, qty: 1)],
      );
    }
  }

  void removeItem(String productId) {
    state = state.copyWith(
      items: state.items.where((e) => e.item.productId != productId).toList(),
    );
  }

  void updateQty(String productId, double qty) {
    if (qty <= 0) {
      removeItem(productId);
      return;
    }
    final updated = state.items.map((e) {
      if (e.item.productId == productId) return e.copyWith(qty: qty);
      return e;
    }).toList();
    state = state.copyWith(items: updated);
  }

  void setPaymentMethod(String method) {
    state = state.copyWith(paymentMethod: method);
  }

  void clear() => state = const CartState();
}

final cartProvider =
    StateNotifierProvider.autoDispose<CartNotifier, CartState>(
  (ref) => CartNotifier(),
);

// ---------------------------------------------------------------------------
// Checkout holati

sealed class CheckoutState {
  const CheckoutState();
}

class CheckoutIdle extends CheckoutState {
  const CheckoutIdle();
}

class CheckoutLoading extends CheckoutState {
  const CheckoutLoading();
}

class CheckoutSuccess extends CheckoutState {
  const CheckoutSuccess({required this.response});
  final PosSaleResponse response;
}

class CheckoutFailure extends CheckoutState {
  const CheckoutFailure({
    required this.message,
    this.isExpiredError = false,
  });
  final String message;

  /// true = 422 pos.product_expired — maxsus qizil ogohlantirish
  final bool isExpiredError;
}

/// Checkout notifier — POST /pos/sales
class CheckoutNotifier extends StateNotifier<CheckoutState> {
  CheckoutNotifier(this._repository) : super(const CheckoutIdle());

  final PosRepository _repository;

  Future<void> checkout(CartState cart) async {
    if (cart.items.isEmpty) return;

    state = const CheckoutLoading();
    try {
      final request = PosSaleRequest(
        // FAQAT product_id + qty — narx YUBORILMAYDI (server hisoblaydi)
        items: cart.items
            .map((e) => PosSaleItem(
                  productId: e.item.productId,
                  qty: e.qty,
                ))
            .toList(),
        paymentMethod: cart.paymentMethod,
      );

      final response = await _repository.createSale(request);
      state = CheckoutSuccess(response: response);
    } on PosProductExpiredException {
      state = const CheckoutFailure(
        message:
            "Mahsulot muddati o'tgan — sotib bo'lmaydi. Inventarni yangilang.",
        isExpiredError: true,
      );
    } on Exception catch (e) {
      state = CheckoutFailure(message: e.toString());
    }
  }

  void reset() => state = const CheckoutIdle();
}

final checkoutProvider =
    StateNotifierProvider.autoDispose<CheckoutNotifier, CheckoutState>(
  (ref) {
    final repository = ref.watch(posRepositoryProvider);
    return CheckoutNotifier(repository);
  },
);

// ---------------------------------------------------------------------------
// Kunlik hisobot

/// Tanlangan sana (YYYY-MM-DD). Null = bugun.
final posSummaryDateProvider =
    StateProvider.autoDispose<String?>((ref) => null);

/// GET /pos/summary — kunlik hisobot.
final posSummaryProvider =
    FutureProvider.autoDispose<PosSummary>((ref) async {
  final repository = ref.watch(posRepositoryProvider);
  final date = ref.watch(posSummaryDateProvider);
  return repository.getPosSummary(date: date);
});
