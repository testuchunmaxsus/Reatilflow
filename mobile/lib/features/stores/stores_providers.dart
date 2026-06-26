import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/local/dao/stores_dao.dart';
import '../../data/local/database.dart';
import '../../data/local/database_provider.dart';
import '../auth/auth_providers.dart';
import 'store_repository.dart';

/// StoreRepository provider
final storeRepositoryProvider = Provider<StoreRepository>((ref) {
  final db = ref.watch(databaseProvider);
  final apiClient = ref.watch(apiClientProvider);
  return StoreRepository(db: db, apiClient: apiClient);
});

/// StoresDao provider
final storesDaoProvider = Provider<StoresDao>((ref) {
  final db = ref.watch(databaseProvider);
  return StoresDao(db);
});

/// Barcha do'konlar stream (offline, Drift'dan)
final storesStreamProvider = StreamProvider<List<Store>>((ref) {
  final dao = ref.watch(storesDaoProvider);
  return dao.watchAll();
});

/// Agent ID bo'yicha do'konlar stream
final storesByAgentProvider =
    StreamProvider.family<List<Store>, String>((ref, agentId) {
  final dao = ref.watch(storesDaoProvider);
  return dao.watchByAgentId(agentId);
});

/// Bitta do'kon (future)
final storeByIdProvider = FutureProvider.family<Store?, String>((ref, id) {
  final dao = ref.watch(storesDaoProvider);
  return dao.getById(id);
});

/// Qidiruv holati
class StoreSearchNotifier extends StateNotifier<String> {
  StoreSearchNotifier() : super('');

  void setQuery(String query) => state = query;
  void clear() => state = '';
}

final storeSearchProvider =
    StateNotifierProvider.autoDispose<StoreSearchNotifier, String>(
  (ref) => StoreSearchNotifier(),
);

/// Filtr qilingan do'konlar (qidiruv bilan)
final filteredStoresProvider =
    StreamProvider.family<List<Store>, String>((ref, agentId) {
  final query = ref.watch(storeSearchProvider);
  final storesAsync = ref.watch(storesByAgentProvider(agentId));

  return storesAsync.when(
    data: (stores) {
      if (query.isEmpty) return Stream.value(stores);
      final lower = query.toLowerCase();
      return Stream.value(
        stores
            .where(
              (s) =>
                  s.name.toLowerCase().contains(lower) ||
                  (s.address?.toLowerCase().contains(lower) ?? false) ||
                  (s.phone?.toLowerCase().contains(lower) ?? false),
            )
            .toList(),
      );
    },
    loading: () => Stream.value([]),
    error: (e, _) => Stream.error(e),
  );
});
