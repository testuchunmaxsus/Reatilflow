import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../data/sync/sync_notifier.dart';
import '../auth/auth_providers.dart';
import '../auth/auth_repository.dart';
import 'connectivity_banner.dart';
import 'sync_providers.dart';

/// Asosiy shell — barcha himoyalangan sahifalar uchun wrapper.
///
/// Tepada ConnectivityBanner (offline holat ko'rsatkichi).
/// Agent uchun pastda NavBar (do'konlar, katalog, buyurtmalar, davomat, bosh).
class HomeShell extends ConsumerWidget {
  const HomeShell({super.key, required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final syncState = ref.watch(syncNotifierProvider);
    final authState = ref.watch(authNotifierProvider);

    final role = switch (authState) {
      AuthStateAuthenticated(:final user) => user.role,
      _ => null,
    };

    final isAgent = role == 'agent';
    final isCourier = role == 'courier';

    return Scaffold(
      appBar: AppBar(
        title: const Text('RETAIL'),
        actions: [
          // Sync holat indikatori
          _SyncStatusIcon(syncState: syncState),
          IconButton(
            icon: const Icon(Icons.logout),
            tooltip: 'Chiqish',
            onPressed: () async {
              await ref.read(authNotifierProvider.notifier).logout();
            },
          ),
        ],
      ),
      body: Column(
        children: [
          const ConnectivityBanner(),
          Expanded(child: child),
        ],
      ),
      // Rol bo'yicha pastki navigatsiya
      bottomNavigationBar: isAgent
          ? _AgentNavBar()
          : isCourier
              ? _CourierNavBar()
              : null,
    );
  }
}

class _SyncStatusIcon extends StatelessWidget {
  const _SyncStatusIcon({required this.syncState});
  final SyncState syncState;

  @override
  Widget build(BuildContext context) {
    return switch (syncState) {
      SyncState.syncing => const Padding(
          padding: EdgeInsets.all(12),
          child: SizedBox(
            width: 20,
            height: 20,
            child: CircularProgressIndicator(strokeWidth: 2),
          ),
        ),
      SyncState.offline => const Icon(Icons.cloud_off, color: Colors.orange),
      SyncState.error => const Icon(Icons.sync_problem, color: Colors.red),
      SyncState.success => const Icon(Icons.cloud_done, color: Colors.green),
      SyncState.idle => const Icon(Icons.cloud_queue),
    };
  }
}

/// Agent pastki navigatsiya paneli
class _AgentNavBar extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final location = GoRouterState.of(context).matchedLocation;

    int currentIndex = 0;
    if (location.startsWith('/home/stores')) currentIndex = 1;
    if (location.startsWith('/home/catalog')) currentIndex = 2;
    if (location.startsWith('/home/orders')) currentIndex = 3;
    if (location.startsWith('/home/attendance')) currentIndex = 4;

    return BottomNavigationBar(
      currentIndex: currentIndex,
      type: BottomNavigationBarType.fixed,
      selectedFontSize: 11,
      unselectedFontSize: 10,
      onTap: (index) {
        switch (index) {
          case 0:
            context.go('/home/agent');
          case 1:
            context.go('/home/stores');
          case 2:
            context.go('/home/catalog');
          case 3:
            context.go('/home/orders');
          case 4:
            context.go('/home/attendance');
        }
      },
      items: const [
        BottomNavigationBarItem(icon: Icon(Icons.home), label: 'Bosh'),
        BottomNavigationBarItem(icon: Icon(Icons.store), label: "Do'konlar"),
        BottomNavigationBarItem(
            icon: Icon(Icons.inventory_2), label: 'Katalog'),
        BottomNavigationBarItem(
            icon: Icon(Icons.receipt_long), label: 'Buyurtmalar'),
        BottomNavigationBarItem(
            icon: Icon(Icons.fingerprint), label: 'Davomat'),
      ],
    );
  }
}

/// Kuryer pastki navigatsiya paneli (T20)
class _CourierNavBar extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final location = GoRouterState.of(context).matchedLocation;

    int currentIndex = 0;
    if (location.startsWith('/home/deliveries')) currentIndex = 1;
    if (location.startsWith('/home/attendance')) currentIndex = 2;

    return BottomNavigationBar(
      currentIndex: currentIndex,
      type: BottomNavigationBarType.fixed,
      selectedFontSize: 11,
      unselectedFontSize: 10,
      onTap: (index) {
        switch (index) {
          case 0:
            context.go('/home/courier');
          case 1:
            context.go('/home/deliveries');
          case 2:
            context.go('/home/attendance');
        }
      },
      items: const [
        BottomNavigationBarItem(icon: Icon(Icons.home), label: 'Bosh'),
        BottomNavigationBarItem(
            icon: Icon(Icons.local_shipping), label: 'Yetkazishlar'),
        BottomNavigationBarItem(
            icon: Icon(Icons.fingerprint), label: 'Davomat'),
      ],
    );
  }
}
