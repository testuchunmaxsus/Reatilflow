import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/app_card.dart';
import '../../core/widgets/dashboard_header.dart';
import '../../core/widgets/section_header.dart';
import '../../core/widgets/stat_card.dart';
import '../../data/sync/sync_notifier.dart';
import '../auth/auth_providers.dart';
import '../auth/auth_repository.dart';
import '../home/sync_providers.dart';

/// Buxgalter uchun bosh ekran — dashboard.
///
/// Ko'rsatiladi:
///   - DashboardHeader (salom, ism, rol)
///   - Moliya umumiy StatCard
///   - Tezkor harakatlar grid
class AccountantDashboard extends ConsumerWidget {
  const AccountantDashboard({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final authState = ref.watch(authNotifierProvider);
    final user = switch (authState) {
      AuthStateAuthenticated(:final user) => user,
      _ => null,
    };

    final syncState = ref.watch(syncNotifierProvider);

    final initials = user != null
        ? user.fullName
            .trim()
            .split(' ')
            .take(2)
            .map((w) => w.isNotEmpty ? w[0] : '')
            .join()
            .toUpperCase()
        : 'BX';

    return SingleChildScrollView(
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header
          DashboardHeader(
            greeting: 'Salom,',
            name: user?.fullName ?? 'Buxgalter',
            subtitle: _formattedDate(),
            role: 'BUXGALTER',
            avatarInitials: initials,
            trailing: _SyncStatusButton(syncState: syncState, ref: ref),
          ),

          const SizedBox(height: AppSpacing.lg),

          // Moliya statistika kartasi
          _FinanceStatCard(),

          const SizedBox(height: AppSpacing.lg),

          // Tezkor harakatlar
          SectionHeader(
            title: 'Tezkor harakatlar',
            subtitle: 'Moliya va buxgalteriya',
          ),
          const SizedBox(height: AppSpacing.sm),

          _AccountantQuickActions(),

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

/// Moliya umumiy StatCard.
class _FinanceStatCard extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final appColors = AppTheme.colorsOf(context);

    return StatCard(
      icon: Icons.account_balance_rounded,
      label: 'Moliya moduli',
      value: 'Balans va yozuvlar',
      subtitle: 'Ko\'rish uchun bosing',
      accentColor: appColors.info,
      onTap: () => Navigator.of(context).pushNamed('/home/accountant/finance'),
    );
  }
}

/// Sync holati tugmasi — DashboardHeader trailing uchun.
class _SyncStatusButton extends StatelessWidget {
  const _SyncStatusButton({required this.syncState, required this.ref});
  final SyncState syncState;
  final WidgetRef ref;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final appColors = AppTheme.colorsOf(context);

    final (icon, color) = switch (syncState) {
      SyncState.syncing => (Icons.sync, cs.onPrimary),
      SyncState.success => (Icons.cloud_done, appColors.success),
      SyncState.error => (Icons.sync_problem, appColors.danger),
      SyncState.offline => (Icons.cloud_off, appColors.warning),
      SyncState.idle => (Icons.cloud_queue, cs.onPrimary.withValues(alpha: 0.7)),
    };

    return GestureDetector(
      onTap: () => ref.read(syncNotifierProvider.notifier).triggerSync(),
      child: syncState == SyncState.syncing
          ? SizedBox(
              width: AppSpacing.iconMd,
              height: AppSpacing.iconMd,
              child: CircularProgressIndicator(
                strokeWidth: 2,
                color: cs.onPrimary,
              ),
            )
          : Icon(icon, color: color, size: AppSpacing.iconMd),
    );
  }
}

/// Buxgalter tezkor harakatlar gridi.
class _AccountantQuickActions extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final actions = const <_QuickActionData>[
      _QuickActionData(
        icon: Icons.account_balance_wallet_rounded,
        label: 'Moliya',
        route: '/home/accountant/finance',
      ),
      _QuickActionData(
        icon: Icons.receipt_long_rounded,
        label: 'Ledger',
        route: '/home/accountant/finance',
      ),
      _QuickActionData(
        icon: Icons.fingerprint,
        label: 'Davomat',
        route: '/home/attendance',
      ),
      _QuickActionData(
        icon: Icons.bar_chart_rounded,
        label: 'Hisobotlar',
        route: '/home/accountant/finance',
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

