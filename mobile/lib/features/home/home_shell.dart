import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_theme.dart';
import '../../data/sync/sync_notifier.dart';
import '../auth/auth_providers.dart';
import '../auth/auth_repository.dart';
import '../enterprise/enterprise_providers.dart';
import 'connectivity_banner.dart';
import 'sync_providers.dart';

/// Asosiy shell — barcha himoyalangan sahifalar uchun wrapper.
///
/// Tepada ConnectivityBanner (offline holat ko'rsatkichi).
/// Pastda Material 3 NavigationBar (rol bo'yicha).
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
    final isAccountant = role == 'accountant';

    return Scaffold(
      appBar: AppBar(
        title: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.storefront_rounded,
              color: Theme.of(context).colorScheme.primary,
              size: AppSpacing.iconMd,
            ),
            const SizedBox(width: AppSpacing.xs),
            const Text('RETAIL'),
          ],
        ),
        actions: [
          // Sync holat indikatori
          _SyncStatusIcon(syncState: syncState, ref: ref),
          IconButton(
            icon: const Icon(Icons.logout_rounded),
            tooltip: 'Chiqish',
            onPressed: () async {
              await ref.read(authNotifierProvider.notifier).logout();
            },
          ),
          const SizedBox(width: AppSpacing.xs),
        ],
      ),
      body: Column(
        children: [
          const ConnectivityBanner(),
          Expanded(child: child),
        ],
      ),
      // Rol bo'yicha Material 3 NavigationBar
      bottomNavigationBar: isAgent
          ? _AgentNavBar()
          : isCourier
              ? _CourierNavBar()
              : isStore
                  ? _StoreNavBar()
                  : isAccountant
                      ? _AccountantNavBar()
                      : null,
    );
  }
}

/// Sync holat ikona — tap qilinganda qayta sinxronlashtiradi.
class _SyncStatusIcon extends StatelessWidget {
  const _SyncStatusIcon({required this.syncState, required this.ref});
  final SyncState syncState;
  final WidgetRef ref;

  @override
  Widget build(BuildContext context) {
    final appColors = AppTheme.colorsOf(context);
    final cs = Theme.of(context).colorScheme;

    if (syncState == SyncState.syncing) {
      return Padding(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: SizedBox(
          width: AppSpacing.iconSm,
          height: AppSpacing.iconSm,
          child: CircularProgressIndicator(
            strokeWidth: 2,
            color: cs.primary,
          ),
        ),
      );
    }

    final (icon, color) = switch (syncState) {
      SyncState.offline => (Icons.cloud_off_rounded, appColors.warning),
      SyncState.error => (Icons.sync_problem_rounded, appColors.danger),
      SyncState.success => (Icons.cloud_done_rounded, appColors.success),
      _ => (Icons.cloud_queue_rounded, cs.onSurfaceVariant),
    };

    return IconButton(
      icon: Icon(icon, color: color),
      tooltip: 'Sinxronlashtirish',
      onPressed: () => ref.read(syncNotifierProvider.notifier).triggerSync(),
    );
  }
}

// ---- NavigationBar-lar ----

/// Agent — Material 3 NavigationBar.
class _AgentNavBar extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final location = GoRouterState.of(context).matchedLocation;

    final hasCatalog = ref.watch(moduleEnabledProvider('catalog'));
    final hasOrders = ref.watch(moduleEnabledProvider('orders'));
    final hasAttendance = ref.watch(moduleEnabledProvider('attendance'));

    final tabs = <_NavTab>[
      const _NavTab(
        route: '/home/agent',
        matchPrefix: '/home/agent',
        icon: Icons.home_outlined,
        selectedIcon: Icons.home_rounded,
        label: 'Bosh',
      ),
      const _NavTab(
        route: '/home/stores',
        matchPrefix: '/home/stores',
        icon: Icons.store_outlined,
        selectedIcon: Icons.store_rounded,
        label: "Do'konlar",
      ),
      if (hasCatalog)
        const _NavTab(
          route: '/home/catalog',
          matchPrefix: '/home/catalog',
          icon: Icons.inventory_2_outlined,
          selectedIcon: Icons.inventory_2_rounded,
          label: 'Katalog',
        ),
      if (hasOrders)
        const _NavTab(
          route: '/home/orders',
          matchPrefix: '/home/orders',
          icon: Icons.receipt_long_outlined,
          selectedIcon: Icons.receipt_long_rounded,
          label: 'Buyurtmalar',
        ),
      if (hasAttendance)
        const _NavTab(
          route: '/home/attendance',
          matchPrefix: '/home/attendance',
          icon: Icons.fingerprint,
          selectedIcon: Icons.fingerprint,
          label: 'Davomat',
        ),
      const _NavTab(
        route: '/home/agent/cabinet',
        matchPrefix: '/home/agent/cabinet',
        icon: Icons.manage_accounts_outlined,
        selectedIcon: Icons.manage_accounts_rounded,
        label: 'Kabinet',
      ),
    ];

    final currentIndex = _resolveIndex(tabs, location);

    return NavigationBar(
      selectedIndex: currentIndex,
      onDestinationSelected: (index) => context.go(tabs[index].route),
      destinations: tabs
          .map((t) => NavigationDestination(
                icon: Icon(t.icon),
                selectedIcon: Icon(t.selectedIcon),
                label: t.label,
              ))
          .toList(),
    );
  }
}

/// Kuryer — Material 3 NavigationBar.
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
        icon: Icons.home_outlined,
        selectedIcon: Icons.home_rounded,
        label: 'Bosh',
      ),
      if (hasDelivery)
        const _NavTab(
          route: '/home/deliveries',
          matchPrefix: '/home/deliveries',
          icon: Icons.local_shipping_outlined,
          selectedIcon: Icons.local_shipping_rounded,
          label: 'Yetkazishlar',
        ),
      if (hasMarketplace)
        const _NavTab(
          route: '/home/courier/mp-deliveries',
          matchPrefix: '/home/courier/mp-deliveries',
          icon: Icons.storefront_outlined,
          selectedIcon: Icons.storefront_rounded,
          label: 'MP Yetkazish',
        ),
      if (hasAttendance)
        const _NavTab(
          route: '/home/attendance',
          matchPrefix: '/home/attendance',
          icon: Icons.fingerprint,
          selectedIcon: Icons.fingerprint,
          label: 'Davomat',
        ),
    ];

    final currentIndex = _resolveIndex(tabs, location);

    return NavigationBar(
      selectedIndex: currentIndex,
      onDestinationSelected: (index) => context.go(tabs[index].route),
      destinations: tabs
          .map((t) => NavigationDestination(
                icon: Icon(t.icon),
                selectedIcon: Icon(t.selectedIcon),
                label: t.label,
              ))
          .toList(),
    );
  }
}

/// Do'kon — Material 3 NavigationBar.
class _StoreNavBar extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final location = GoRouterState.of(context).matchedLocation;

    final hasPos = ref.watch(moduleEnabledProvider('pos'));
    final hasMarketplace = ref.watch(moduleEnabledProvider('marketplace'));
    final hasFinance = ref.watch(moduleEnabledProvider('finance'));
    final hasDelivery = ref.watch(moduleEnabledProvider('delivery'));

    final tabs = <_NavTab>[
      const _NavTab(
        route: '/home/store',
        matchPrefix: '/home/store',
        icon: Icons.home_outlined,
        selectedIcon: Icons.home_rounded,
        label: 'Bosh',
      ),
      if (hasPos) ...[
        const _NavTab(
          route: '/home/pos/sale',
          matchPrefix: '/home/pos/sale',
          icon: Icons.point_of_sale_outlined,
          selectedIcon: Icons.point_of_sale_rounded,
          label: 'Sotuv',
        ),
        const _NavTab(
          route: '/home/pos/inventory',
          matchPrefix: '/home/pos/inventory',
          icon: Icons.inventory_2_outlined,
          selectedIcon: Icons.inventory_2_rounded,
          label: 'Inventar',
        ),
      ],
      if (hasMarketplace)
        const _NavTab(
          route: '/home/marketplace',
          matchPrefix: '/home/marketplace',
          icon: Icons.storefront_outlined,
          selectedIcon: Icons.storefront_rounded,
          label: 'Marketplace',
        ),
      if (hasFinance)
        const _NavTab(
          route: '/home/store/balance',
          matchPrefix: '/home/store/balance',
          icon: Icons.account_balance_wallet_outlined,
          selectedIcon: Icons.account_balance_wallet_rounded,
          label: 'Balans',
        ),
      if (hasDelivery)
        const _NavTab(
          route: '/home/store/deliveries',
          matchPrefix: '/home/store/deliveries',
          icon: Icons.local_shipping_outlined,
          selectedIcon: Icons.local_shipping_rounded,
          label: 'Yetkazish',
        ),
    ];

    final currentIndex = _resolveIndex(tabs, location);

    return NavigationBar(
      selectedIndex: currentIndex,
      onDestinationSelected: (index) => context.go(tabs[index].route),
      destinations: tabs
          .map((t) => NavigationDestination(
                icon: Icon(t.icon),
                selectedIcon: Icon(t.selectedIcon),
                label: t.label,
              ))
          .toList(),
    );
  }
}

/// Buxgalter — Material 3 NavigationBar.
class _AccountantNavBar extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final location = GoRouterState.of(context).matchedLocation;

    final tabs = <_NavTab>[
      const _NavTab(
        route: '/home/accountant',
        matchPrefix: '/home/accountant',
        icon: Icons.home_outlined,
        selectedIcon: Icons.home_rounded,
        label: 'Bosh',
      ),
      const _NavTab(
        route: '/home/accountant/finance',
        matchPrefix: '/home/accountant/finance',
        icon: Icons.account_balance_wallet_outlined,
        selectedIcon: Icons.account_balance_wallet_rounded,
        label: 'Moliya',
      ),
      const _NavTab(
        route: '/home/attendance',
        matchPrefix: '/home/attendance',
        icon: Icons.fingerprint,
        selectedIcon: Icons.fingerprint,
        label: 'Davomat',
      ),
    ];

    final currentIndex = _resolveIndex(tabs, location);

    return NavigationBar(
      selectedIndex: currentIndex,
      onDestinationSelected: (index) => context.go(tabs[index].route),
      destinations: tabs
          .map((t) => NavigationDestination(
                icon: Icon(t.icon),
                selectedIcon: Icon(t.selectedIcon),
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
    required this.selectedIcon,
    required this.label,
  });

  final String route;
  final String matchPrefix;
  final IconData icon;
  final IconData selectedIcon;
  final String label;
}

/// Eng uzun mos keluvchi matchPrefix bo'yicha tab indeksini aniqlaydi.
///
/// Bu usul `/home/agent` va `/home/agent/cabinet` kabi ichma-ich yo'llar
/// mavjud bo'lganda aniq tabni ajratib ko'rsatadi.
int _resolveIndex(List<_NavTab> tabs, String location) {
  int bestIndex = 0;
  int bestLength = 0;
  for (int i = 0; i < tabs.length; i++) {
    final prefix = tabs[i].matchPrefix;
    if (location.startsWith(prefix) && prefix.length > bestLength) {
      bestIndex = i;
      bestLength = prefix.length;
    }
  }
  return bestIndex;
}
