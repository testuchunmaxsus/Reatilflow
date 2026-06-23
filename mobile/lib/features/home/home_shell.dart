import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../data/sync/sync_notifier.dart';
import '../auth/auth_providers.dart';
import '../auth/auth_repository.dart';
import '../enterprise/enterprise_providers.dart';
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
    final isStore = role == 'store';

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
              : isStore
                  ? _StoreNavBar()
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

/// Agent pastki navigatsiya paneli — enabled_modules'ga qarab tab'lar.
class _AgentNavBar extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final location = GoRouterState.of(context).matchedLocation;

    final hasCatalog = ref.watch(moduleEnabledProvider('catalog'));
    final hasOrders = ref.watch(moduleEnabledProvider('orders'));
    final hasAttendance = ref.watch(moduleEnabledProvider('attendance'));

    // Tab ro'yxatini dinamik yasash
    final tabs = <_NavTab>[
      const _NavTab(
        route: '/home/agent',
        matchPrefix: '/home/agent',
        icon: Icons.home,
        label: 'Bosh',
      ),
      const _NavTab(
        route: '/home/stores',
        matchPrefix: '/home/stores',
        icon: Icons.store,
        label: "Do'konlar",
      ),
      if (hasCatalog)
        const _NavTab(
          route: '/home/catalog',
          matchPrefix: '/home/catalog',
          icon: Icons.inventory_2,
          label: 'Katalog',
        ),
      if (hasOrders)
        const _NavTab(
          route: '/home/orders',
          matchPrefix: '/home/orders',
          icon: Icons.receipt_long,
          label: 'Buyurtmalar',
        ),
      if (hasAttendance)
        const _NavTab(
          route: '/home/attendance',
          matchPrefix: '/home/attendance',
          icon: Icons.fingerprint,
          label: 'Davomat',
        ),
    ];

    final currentIndex = _resolveIndex(tabs, location);

    return BottomNavigationBar(
      currentIndex: currentIndex,
      type: BottomNavigationBarType.fixed,
      selectedFontSize: 11,
      unselectedFontSize: 10,
      onTap: (index) => context.go(tabs[index].route),
      items: tabs
          .map((t) => BottomNavigationBarItem(
                icon: Icon(t.icon),
                label: t.label,
              ))
          .toList(),
    );
  }
}

/// Kuryer pastki navigatsiya paneli — enabled_modules'ga qarab tab'lar.
class _CourierNavBar extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final location = GoRouterState.of(context).matchedLocation;

    final hasDelivery = ref.watch(moduleEnabledProvider('delivery'));
    final hasAttendance = ref.watch(moduleEnabledProvider('attendance'));
    final hasMarketplace = ref.watch(moduleEnabledProvider('marketplace'));

    final tabs = <_NavTab>[
      const _NavTab(
        route: '/home/courier',
        matchPrefix: '/home/courier',
        icon: Icons.home,
        label: 'Bosh',
      ),
      if (hasDelivery)
        const _NavTab(
          route: '/home/deliveries',
          matchPrefix: '/home/deliveries',
          icon: Icons.local_shipping,
          label: 'Yetkazishlar',
        ),
      if (hasMarketplace)
        const _NavTab(
          route: '/home/courier/mp-deliveries',
          matchPrefix: '/home/courier/mp-deliveries',
          icon: Icons.storefront,
          label: 'MP Yetkazish',
        ),
      if (hasAttendance)
        const _NavTab(
          route: '/home/attendance',
          matchPrefix: '/home/attendance',
          icon: Icons.fingerprint,
          label: 'Davomat',
        ),
    ];

    final currentIndex = _resolveIndex(tabs, location);

    return BottomNavigationBar(
      currentIndex: currentIndex,
      type: BottomNavigationBarType.fixed,
      selectedFontSize: 11,
      unselectedFontSize: 10,
      onTap: (index) => context.go(tabs[index].route),
      items: tabs
          .map((t) => BottomNavigationBarItem(
                icon: Icon(t.icon),
                label: t.label,
              ))
          .toList(),
    );
  }
}

/// Do'kon (store) pastki navigatsiya paneli — pos moduli gating.
class _StoreNavBar extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final location = GoRouterState.of(context).matchedLocation;

    final hasPos = ref.watch(moduleEnabledProvider('pos'));
    final hasMarketplace = ref.watch(moduleEnabledProvider('marketplace'));

    final tabs = <_NavTab>[
      const _NavTab(
        route: '/home/store',
        matchPrefix: '/home/store',
        icon: Icons.home,
        label: 'Bosh',
      ),
      if (hasPos) ...[
        const _NavTab(
          route: '/home/pos/sale',
          matchPrefix: '/home/pos/sale',
          icon: Icons.point_of_sale,
          label: 'Sotuv',
        ),
        const _NavTab(
          route: '/home/pos/inventory',
          matchPrefix: '/home/pos/inventory',
          icon: Icons.inventory_2_outlined,
          label: 'Inventar',
        ),
      ],
      if (hasMarketplace)
        const _NavTab(
          route: '/home/marketplace',
          matchPrefix: '/home/marketplace',
          icon: Icons.storefront,
          label: 'Marketplace',
        ),
    ];

    final currentIndex = _resolveIndex(tabs, location);

    return BottomNavigationBar(
      currentIndex: currentIndex,
      type: BottomNavigationBarType.fixed,
      selectedFontSize: 11,
      unselectedFontSize: 10,
      onTap: (index) => context.go(tabs[index].route),
      items: tabs
          .map((t) => BottomNavigationBarItem(
                icon: Icon(t.icon),
                label: t.label,
              ))
          .toList(),
    );
  }
}

// ---- Yordamchi ----

class _NavTab {
  const _NavTab({
    required this.route,
    required this.matchPrefix,
    required this.icon,
    required this.label,
  });

  final String route;
  final String matchPrefix;
  final IconData icon;
  final String label;
}

int _resolveIndex(List<_NavTab> tabs, String location) {
  for (int i = 0; i < tabs.length; i++) {
    if (location.startsWith(tabs[i].matchPrefix)) return i;
  }
  return 0;
}
