import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/local/database_provider.dart';
import '../../data/sync/sync_notifier.dart';
import '../../data/sync/sync_service.dart';
import '../auth/auth_providers.dart';

/// SyncService provider
final syncServiceProvider = Provider<SyncService>((ref) {
  final db = ref.watch(databaseProvider);
  final apiClient = ref.watch(apiClientProvider);
  return SyncService(db: db, apiClient: apiClient);
});

/// SyncNotifier provider
final syncNotifierProvider =
    StateNotifierProvider<SyncNotifier, SyncState>((ref) {
  final syncService = ref.watch(syncServiceProvider);
  return SyncNotifier(
    syncService: syncService,
    connectivity: Connectivity(),
  );
});
