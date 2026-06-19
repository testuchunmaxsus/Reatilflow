import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'sync_service.dart';

/// Sync holati
enum SyncState { idle, syncing, success, error, offline }

/// Riverpod StateNotifier — sync oqimini boshqaradi.
///
/// Tarmoq ulanishi o'zgarganda avtomatik sync ishga tushiradi.
/// UI ConnectivityBanner uchun holat kuzatadi.
class SyncNotifier extends StateNotifier<SyncState> {
  SyncNotifier({
    required SyncService syncService,
    required Connectivity connectivity,
  })  : _syncService = syncService,
        _connectivity = connectivity,
        super(SyncState.idle) {
    _startConnectivityWatch();
  }

  final SyncService _syncService;
  final Connectivity _connectivity;
  StreamSubscription<List<ConnectivityResult>>? _connectivitySub;
  Timer? _periodicTimer;

  bool _isOnline = false;

  void _startConnectivityWatch() {
    _connectivity.onConnectivityChanged.listen((results) {
      final online = results.any(
        (r) => r != ConnectivityResult.none,
      );

      if (online && !_isOnline) {
        // Tarmoq tiklandi — sync ishga tushir
        _isOnline = true;
        triggerSync();
      } else if (!online) {
        _isOnline = false;
        state = SyncState.offline;
      }
    });

    // Periodik sync (5 daqiqada bir)
    _periodicTimer = Timer.periodic(const Duration(minutes: 5), (_) {
      if (_isOnline) triggerSync();
    });

    // Boshlang'ich tarmoq holatini tekshirish
    _connectivity.checkConnectivity().then((results) {
      _isOnline = results.any((r) => r != ConnectivityResult.none);
      if (!_isOnline) state = SyncState.offline;
    });
  }

  /// Manual sync trigger (pull-to-refresh yoki fon)
  Future<void> triggerSync() async {
    if (state == SyncState.syncing) return;

    state = SyncState.syncing;
    final result = await _syncService.sync();

    switch (result) {
      case SyncResult.success:
        state = SyncState.success;
      case SyncResult.partial:
        state = SyncState.error;
      case SyncResult.networkError:
        state = _isOnline ? SyncState.error : SyncState.offline;
      case SyncResult.authError:
        state = SyncState.error;
    }
  }

  @override
  void dispose() {
    _connectivitySub?.cancel();
    _periodicTimer?.cancel();
    super.dispose();
  }
}
