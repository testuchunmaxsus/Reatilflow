import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/router/app_router.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/widgets/app_card.dart';
import '../../core/widgets/dashboard_header.dart';
import '../../core/widgets/empty_state.dart';
import '../../core/widgets/section_header.dart';
import '../auth/auth_providers.dart';
import '../auth/auth_repository.dart';
import '../enterprise/enterprise_providers.dart';

/// Do'kon roli uchun bosh ekran — dashboard.
///
/// Tezkor harakatlar:
/// - POS Sotuv (pos moduli yoqilganda)
/// - Inventar (pos moduli yoqilganda)
/// - Kunlik hisobot (pos moduli yoqilganda)
class StoreDashboard extends ConsumerWidget {
  const StoreDashboard({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final authState = ref.watch(authNotifierProvider);
    final user = switch (authState) {
      AuthStateAuthenticated(:final user) => user,
      _ => null,
    };

    final hasPos = ref.watch(moduleEnabledProvider('pos'));
    final hasFinance = ref.watch(moduleEnabledProvider('finance'));
    final hasDelivery = ref.watch(moduleEnabledProvider('delivery'));

    final initials = user != null
        ? user.fullName
            .trim()
            .split(' ')
            .take(2)
            .map((w) => w.isNotEmpty ? w[0] : '')
            .join()
            .toUpperCase()
        : 'DO';

    return SingleChildScrollView(
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header
          DashboardHeader(
            greeting: 'Salom,',
            name: user?.fullName ?? "Do'kon",
            subtitle: _formattedDate(),
            role: "DO'KON",
            avatarInitials: initials,
          ),

          const SizedBox(height: AppSpacing.lg),

          // POS moduli yo'q bo'lsa — EmptyState
          if (!hasPos)
            EmptyState(
              icon: Icons.point_of_sale_outlined,
              title: 'POS moduli faollashtirilmagan',
              message:
                  'Administrator POS modulini yoqishi kerak. '
                  'Iltimos, administrator bilan bog\'laning.',
            )
          else ...[
            SectionHeader(
              title: 'Tezkor harakatlar',
              subtitle: 'Do\'kon operatsiyalari',
            ),
            const SizedBox(height: AppSpacing.sm),

            _StoreQuickActions(
              hasFinance: hasFinance,
              hasDelivery: hasDelivery,
            ),
          ],

          const SizedBox(height: AppSpacing.lg),
        ],
      ),
    );
  }

  String _formattedDate() {
    final now = DateTime.now();
    const months = [
      'yanvar', 'fevral', 'mart', 'aprel', 'may', 'iyun',
      'iyul', 'avgust', 'sentabr', 'oktabr', 'noyabr', 'dekabr',
    ];
    return '${now.day} ${months[now.month - 1]} ${now.year}';
  }
}

/// Do'kon tezkor harakatlar gridi.
class _StoreQuickActions extends StatelessWidget {
  const _StoreQuickActions({
    required this.hasFinance,
    required this.hasDelivery,
  });

  final bool hasFinance;
  final bool hasDelivery;

  @override
  Widget build(BuildContext context) {
    final actions = <_QuickActionData>[
      const _QuickActionData(
        icon: Icons.point_of_sale_rounded,
        label: 'Sotuv',
        route: '/home/pos/sale',
      ),
      const _QuickActionData(
        icon: Icons.inventory_2_rounded,
        label: 'Inventar',
        route: '/home/pos/inventory',
      ),
      const _QuickActionData(
        icon: Icons.bar_chart_rounded,
        label: 'Hisobot',
        route: '/home/pos/summary',
      ),
      if (hasFinance)
        _QuickActionData(
          icon: Icons.account_balance_wallet_rounded,
          label: 'Balans',
          route: routeStoreBalance,
        ),
      if (hasDelivery)
        _QuickActionData(
          icon: Icons.local_shipping_rounded,
          label: 'Yetkazish',
          route: routeStoreDeliveries,
        ),
    ];

    return GridView.count(
      crossAxisCount: 2,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      mainAxisSpacing: AppSpacing.sm,
      crossAxisSpacing: AppSpacing.sm,
      childAspectRatio: 1.6,
      children: actions
          .map((a) => _QuickActionCard(
                icon: a.icon,
                label: a.label,
                onTap: () => context.go(a.route),
              ))
          .toList(),
    );
  }
}

class _QuickActionData {
  const _QuickActionData({
    required this.icon,
    required this.label,
    required this.route,
  });
  final IconData icon;
  final String label;
  final String route;
}

class _QuickActionCard extends StatelessWidget {
  const _QuickActionCard({
    required this.icon,
    required this.label,
    required this.onTap,
  });
  final IconData icon;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;

    return AppCard(
      onTap: onTap,
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.md,
      ),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Container(
            width: AppSpacing.iconLg + AppSpacing.sm,
            height: AppSpacing.iconLg + AppSpacing.sm,
            decoration: BoxDecoration(
              color: cs.primaryContainer,
              borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
            ),
            child: Icon(icon, color: cs.primary, size: AppSpacing.iconMd),
          ),
          const SizedBox(height: AppSpacing.xs),
          Text(
            label,
            style: tt.labelMedium?.copyWith(
              color: cs.onSurface,
              fontWeight: FontWeight.w600,
            ),
            textAlign: TextAlign.center,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        ],
      ),
    );
  }
}
