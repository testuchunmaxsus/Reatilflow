import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../auth/auth_providers.dart';
import 'marketplace_models.dart';
import 'marketplace_repository.dart';

// ---------------------------------------------------------------------------
// Repository

final marketplaceRepositoryProvider = Provider<MarketplaceRepository>((ref) {
  final api = ref.watch(apiClientProvider);
  return MarketplaceRepository(apiClient: api);
});

// ---------------------------------------------------------------------------
// Browse — bannerlar

sealed class BannersState {
  const BannersState();
}

class BannersLoading extends BannersState {
  const BannersLoading();
}

class BannersLoaded extends BannersState {
  const BannersLoaded({required this.banners});
  final List<MarketplaceBanner> banners;
}

class BannersError extends BannersState {
  const BannersError({required this.message});
  final String message;
}

class BannersNotifier extends StateNotifier<BannersState> {
  BannersNotifier(this._repository) : super(const BannersLoading()) {
    load();
  }

  final MarketplaceRepository _repository;

  Future<void> load() async {
    state = const BannersLoading();
    try {
      final banners = await _repository.getBanners();
      state = BannersLoaded(banners: banners);
    } on Exception catch (e) {
      state = BannersError(message: e.toString());
    }
  }
}

final bannersNotifierProvider =
    StateNotifierProvider.autoDispose<BannersNotifier, BannersState>(
  (ref) {
    final repo = ref.watch(marketplaceRepositoryProvider);
    return BannersNotifier(repo);
  },
);

// ---------------------------------------------------------------------------
// Browse — aksiyalar

sealed class PromosState {
  const PromosState();
}

class PromosLoading extends PromosState {
  const PromosLoading();
}

class PromosLoaded extends PromosState {
  const PromosLoaded({required this.promos});
  final List<MarketplacePromo> promos;
}

class PromosError extends PromosState {
  const PromosError({required this.message});
  final String message;
}

class PromosNotifier extends StateNotifier<PromosState> {
  PromosNotifier(this._repository) : super(const PromosLoading()) {
    load();
  }

  final MarketplaceRepository _repository;

  Future<void> load() async {
    state = const PromosLoading();
    try {
      final promos = await _repository.getPromos();
      state = PromosLoaded(promos: promos);
    } on Exception catch (e) {
      state = PromosError(message: e.toString());
    }
  }
}

final promosNotifierProvider =
    StateNotifierProvider.autoDispose<PromosNotifier, PromosState>(
  (ref) {
    final repo = ref.watch(marketplaceRepositoryProvider);
    return PromosNotifier(repo);
  },
);

// ---------------------------------------------------------------------------
// Browse — mahsulotlar

/// Qidiruv matni
final marketplaceSearchProvider =
    StateNotifierProvider.autoDispose<_SearchNotifier, String>(
  (ref) => _SearchNotifier(),
);

class _SearchNotifier extends StateNotifier<String> {
  _SearchNotifier() : super('');

  void set(String q) => state = q;
  void clear() => state = '';
}

/// Tanlangan supplier filtri (null = hammasi)
final marketplaceSupplierFilterProvider =
    StateNotifierProvider.autoDispose<_SupplierFilterNotifier, String?>(
  (ref) => _SupplierFilterNotifier(),
);

class _SupplierFilterNotifier extends StateNotifier<String?> {
  _SupplierFilterNotifier() : super(null);

  void set(String? supplierId) => state = supplierId;
  void clear() => state = null;
}

sealed class ProductsState {
  const ProductsState();
}

class ProductsLoading extends ProductsState {
  const ProductsLoading();
}

class ProductsLoaded extends ProductsState {
  const ProductsLoaded({required this.products});
  final List<MarketplaceProduct> products;
}

class ProductsError extends ProductsState {
  const ProductsError({required this.message});
  final String message;
}

class ProductsNotifier extends StateNotifier<ProductsState> {
  ProductsNotifier(this._repository) : super(const ProductsLoading()) {
    load();
  }

  final MarketplaceRepository _repository;

  String? _lastSearch;
  String? _lastSupplier;

  Future<void> load({String? search, String? supplierEnterpriseId}) async {
    _lastSearch = search;
    _lastSupplier = supplierEnterpriseId;
    state = const ProductsLoading();
    try {
      final products = await _repository.getProducts(
        search: search,
        supplierEnterpriseId: supplierEnterpriseId,
      );
      state = ProductsLoaded(products: products);
    } on Exception catch (e) {
      state = ProductsError(message: e.toString());
    }
  }

  Future<void> reload() =>
      load(search: _lastSearch, supplierEnterpriseId: _lastSupplier);
}

final productsNotifierProvider =
    StateNotifierProvider.autoDispose<ProductsNotifier, ProductsState>(
  (ref) {
    final repo = ref.watch(marketplaceRepositoryProvider);
    final notifier = ProductsNotifier(repo);

    // Qidiruv yoki supplier filtri o'zgarganda qayta yuklash
    ref.listen(marketplaceSearchProvider, (_, next) {
      final supplier = ref.read(marketplaceSupplierFilterProvider);
      notifier.load(
          search: next.isEmpty ? null : next,
          supplierEnterpriseId: supplier);
    });

    ref.listen(marketplaceSupplierFilterProvider, (_, next) {
      final search = ref.read(marketplaceSearchProvider);
      notifier.load(
          search: search.isEmpty ? null : search,
          supplierEnterpriseId: next);
    });

    return notifier;
  },
);

// ---------------------------------------------------------------------------
// Savat (marketplace buyurtma uchun)

/// Savat elementi — marketplace mahsuloti.
class MarketplaceCartItem {
  const MarketplaceCartItem({
    required this.product,
    required this.qty,
  });

  final MarketplaceProduct product;
  final double qty;

  MarketplaceCartItem copyWith({
    MarketplaceProduct? product,
    double? qty,
  }) =>
      MarketplaceCartItem(
        product: product ?? this.product,
        qty: qty ?? this.qty,
      );
}

/// Savat holati.
class MarketplaceCartState {
  const MarketplaceCartState({this.items = const []});

  final List<MarketplaceCartItem> items;

  MarketplaceCartState copyWith({List<MarketplaceCartItem>? items}) =>
      MarketplaceCartState(items: items ?? this.items);

  /// Taxminiy jami (server hisoblaydi — faqat display uchun).
  double get estimatedTotal =>
      items.fold(0.0, (sum, e) => sum + e.product.price * e.qty);

  bool get isEmpty => items.isEmpty;
}

class MarketplaceCartNotifier extends StateNotifier<MarketplaceCartState> {
  MarketplaceCartNotifier() : super(const MarketplaceCartState());

  void addItem(MarketplaceProduct product) {
    final idx = state.items.indexWhere((e) => e.product.id == product.id);
    if (idx >= 0) {
      final updated = List<MarketplaceCartItem>.from(state.items);
      updated[idx] = updated[idx].copyWith(qty: updated[idx].qty + 1);
      state = state.copyWith(items: updated);
    } else {
      state = state.copyWith(
        items: [...state.items, MarketplaceCartItem(product: product, qty: 1)],
      );
    }
  }

  void removeItem(String productId) {
    state = state.copyWith(
      items:
          state.items.where((e) => e.product.id != productId).toList(),
    );
  }

  void updateQty(String productId, double qty) {
    if (qty <= 0) {
      removeItem(productId);
      return;
    }
    final updated = state.items.map((e) {
      if (e.product.id == productId) return e.copyWith(qty: qty);
      return e;
    }).toList();
    state = state.copyWith(items: updated);
  }

  void clear() => state = const MarketplaceCartState();
}

final marketplaceCartProvider = StateNotifierProvider.autoDispose<
    MarketplaceCartNotifier, MarketplaceCartState>(
  (ref) => MarketplaceCartNotifier(),
);

// ---------------------------------------------------------------------------
// Buyurtma yaratish

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
  const CreateOrderSuccess({required this.order});
  final MarketplaceOrder order;
}

class CreateOrderFailure extends CreateOrderState {
  const CreateOrderFailure({required this.message});
  final String message;
}

/// Bitta mahsulot → bitta buyurtma notifier.
///
/// Server-avtoritar: faqat product_id + qty yuboriladi.
class CreateMarketplaceOrderNotifier
    extends StateNotifier<CreateOrderState> {
  CreateMarketplaceOrderNotifier(this._repository)
      : super(const CreateOrderIdle());

  final MarketplaceRepository _repository;

  Future<void> createOrder({
    required String productId,
    required double qty,
  }) async {
    state = const CreateOrderLoading();
    try {
      final request = CreateMarketplaceOrderRequest(
        productId: productId,
        qty: qty,
        // Narx YUBORILMAYDI — server hisoblaydi
      );
      final order = await _repository.createOrder(request);
      state = CreateOrderSuccess(order: order);
    } on Exception catch (e) {
      state = CreateOrderFailure(message: e.toString());
    }
  }

  void reset() => state = const CreateOrderIdle();
}

final createMarketplaceOrderProvider = StateNotifierProvider.autoDispose<
    CreateMarketplaceOrderNotifier, CreateOrderState>(
  (ref) {
    final repo = ref.watch(marketplaceRepositoryProvider);
    return CreateMarketplaceOrderNotifier(repo);
  },
);

// ---------------------------------------------------------------------------
// Outgoing buyurtmalar

sealed class OutgoingOrdersState {
  const OutgoingOrdersState();
}

class OutgoingOrdersLoading extends OutgoingOrdersState {
  const OutgoingOrdersLoading();
}

class OutgoingOrdersLoaded extends OutgoingOrdersState {
  const OutgoingOrdersLoaded({required this.orders});
  final List<MarketplaceOrder> orders;
}

class OutgoingOrdersError extends OutgoingOrdersState {
  const OutgoingOrdersError({required this.message});
  final String message;
}

class OutgoingOrdersNotifier extends StateNotifier<OutgoingOrdersState> {
  OutgoingOrdersNotifier(this._repository)
      : super(const OutgoingOrdersLoading()) {
    load();
  }

  final MarketplaceRepository _repository;

  Future<void> load() async {
    state = const OutgoingOrdersLoading();
    try {
      final orders = await _repository.getOutgoingOrders();
      state = OutgoingOrdersLoaded(orders: orders);
    } on Exception catch (e) {
      state = OutgoingOrdersError(message: e.toString());
    }
  }
}

final outgoingOrdersProvider = StateNotifierProvider.autoDispose<
    OutgoingOrdersNotifier, OutgoingOrdersState>(
  (ref) {
    final repo = ref.watch(marketplaceRepositoryProvider);
    return OutgoingOrdersNotifier(repo);
  },
);

// ---------------------------------------------------------------------------
// Qabul qilish

sealed class AcceptOrderState {
  const AcceptOrderState();
}

class AcceptOrderIdle extends AcceptOrderState {
  const AcceptOrderIdle();
}

class AcceptOrderLoading extends AcceptOrderState {
  const AcceptOrderLoading();
}

class AcceptOrderSuccess extends AcceptOrderState {
  const AcceptOrderSuccess({required this.order});
  final MarketplaceOrder order;
}

class AcceptOrderFailure extends AcceptOrderState {
  const AcceptOrderFailure({required this.message});
  final String message;
}

class AcceptOrderNotifier extends StateNotifier<AcceptOrderState> {
  AcceptOrderNotifier(this._repository) : super(const AcceptOrderIdle());

  final MarketplaceRepository _repository;

  Future<void> accept({
    required String orderId,
    required List<AcceptOrderLine> lines,
  }) async {
    state = const AcceptOrderLoading();
    try {
      final request = AcceptOrderRequest(lines: lines);
      final order = await _repository.acceptOrder(
        orderId: orderId,
        request: request,
      );
      state = AcceptOrderSuccess(order: order);
    } on Exception catch (e) {
      state = AcceptOrderFailure(message: e.toString());
    }
  }

  void reset() => state = const AcceptOrderIdle();
}

final acceptOrderProvider = StateNotifierProvider.autoDispose.family<
    AcceptOrderNotifier, AcceptOrderState, String>(
  (ref, orderId) {
    final repo = ref.watch(marketplaceRepositoryProvider);
    return AcceptOrderNotifier(repo);
  },
);

// ---------------------------------------------------------------------------
// Bitta buyurtma (detail uchun)

final marketplaceOrderDetailProvider =
    FutureProvider.autoDispose.family<MarketplaceOrder, String>(
  (ref, orderId) async {
    final repo = ref.watch(marketplaceRepositoryProvider);
    return repo.getOrder(orderId);
  },
);
