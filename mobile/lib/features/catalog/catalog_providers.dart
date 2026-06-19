import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/local/dao/products_dao.dart';
import '../../data/local/database.dart';
import '../../data/local/database_provider.dart';

/// ProductsDao provider
final productsDaoProvider = Provider<ProductsDao>((ref) {
  final db = ref.watch(databaseProvider);
  return ProductsDao(db);
});

/// Barcha faol mahsulotlar stream (offline, Drift'dan)
final productsStreamProvider = StreamProvider<List<Product>>((ref) {
  final dao = ref.watch(productsDaoProvider);
  return dao.watchAllActive();
});

/// Mahsulot qidiruv holati
class ProductSearchNotifier extends StateNotifier<String> {
  ProductSearchNotifier() : super('');

  void setQuery(String query) => state = query;
  void clear() => state = '';
}

final productSearchProvider =
    StateNotifierProvider.autoDispose<ProductSearchNotifier, String>(
  (ref) => ProductSearchNotifier(),
);

/// Filtr qilingan mahsulotlar (qidiruv bilan, Drift search)
final filteredProductsProvider =
    FutureProvider.autoDispose<List<Product>>((ref) async {
  final query = ref.watch(productSearchProvider);
  final dao = ref.watch(productsDaoProvider);

  if (query.isEmpty) {
    return dao.getAllActive();
  }
  return dao.search(query);
});
