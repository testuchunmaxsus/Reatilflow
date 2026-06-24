import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/app_card.dart';
import '../../core/widgets/dashboard_header.dart';
import '../../core/widgets/empty_state.dart';
import '../../core/widgets/section_header.dart';
import '../../core/widgets/stat_card.dart';
import '../../data/sync/sync_notifier.dart';
import '../attendance/attendance_providers.dart';
import '../auth/auth_providers.dart';
import '../auth/auth_repository.dart';
import '../delivery/delivery_providers.dart';
import '../enterprise/enterprise_providers.dart';
import '../home/sync_providers.dart';

/// Kuryer uchun bosh ekran — dashboard.
///
/// Ko'rsatiladi:
/// - DashboardHeader (salom, ism, rol)
/// - Faol yetkazishlar StatCard (delivery moduli yoqilganda)
/// - Davomat StatCard (attendance moduli yoqilganda)
/// - Tezkor harakatlar grid
class CourierDashboard extends ConsumerWidget {
  const CourierDashboard({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final authState = ref.watch(authNotifierProvider);
    final user = switch (authState) {
      AuthStateAuthenticated(:final user) => user,
      _ => null,
    };

    final syncState = ref.watch(syncNotifierProvider);
    final attendanceState = ref.watch(attendanceNotifierProvider);
    final activeCountAsync = ref.watch(activeDeliveriesCountProvider);
    final hasDelivery = ref.watch(moduleEnabledProvider('delivery'));
    final hasAttendance = ref.watch(moduleEnabledProvider('attendance'));
    final hasMarketplace = ref.watch(moduleEnabledProvider('marketplace'));

    final initials = user != null
        ? user.fullName
            .trim()
            .split(' ')
            .take(2)
            .map((w) => w.isNotEmpty ? w[0] : '')
            .join()
            .toUpperCase()
        : 'KR';

    return SingleChildScrollView(
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header
          DashboardHeader(
            greeting: 'Salom,',
            name: user?.fullName ?? 'Kuryer',
            subtitle: _formattedDate(),
            role: 'KURYER',
            avatarInitials: initials,
            trailing: _SyncStatusButton(syncState: syncState, ref: ref),
          ),

          const SizedBox(height: AppSpacing.lg),

          // Statistika qatori
          if (hasDelivery || hasAttendance)
            _StatsRow(
              hasDelivery: hasDelivery,
              hasAttendance: hasAttendance,
              activeCountAsync: activeCountAsync,
              attendanceState: attendanceState,
            ),

          if (hasDelivery || hasAttendance)
            const SizedBox(height: AppSpacing.lg),

          // Tezkor harakatlar
          SectionHeader(
            title: 'Tezkor harakatlar',
            subtitle: 'Tez kirishingiz uchun',
          ),
          const SizedBox(height: AppSpacing.sm),

          _CourierQuickActions(
            hasDelivery: hasDelivery,
            hasAttendance: hasAttendance,
            hasMarketplace: hasMarketplace,
          ),

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

/// Statistika qatori — yetkazish + davomat stat kartalar.
class _StatsRow extends StatelessWidget {
  const _StatsRow({
    required this.hasDelivery,
    required this.hasAttendance,
    required this.activeCountAsync,
    required this.attendanceState,
  });

  final bool hasDelivery;
  final bool hasAttendance;
  final AsyncValue<int> activeCountAsync;
  final AttendanceState attendanceState;

  @override
  Widget build(BuildContext context) {
    final appColors = AppTheme.colorsOf(context);

    final deliveryWidget = hasDelivery
        ? activeCountAsync.when(
            data: (count) => StatCard(
              icon: Icons.local_shipping_rounded,
              label: 'Faol yetkazishlar',
              value: count > 0 ? '$count ta' : 'Yo\'q',
              accentColor: count > 0 ? appColors.info : appColors.warning,
              onTap: () => Navigator.of(context).pushNamed('/home/deliveries'),
            ),
            loading: () => StatCard(
              icon: Icons.local_shipping_rounded,
              label: 'Faol yetkazishlar',
              value: '—',
              isLoading: true,
            ),
            error: (_, __) => const SizedBox.shrink(),
          )
        : null;

    final attendanceWidget = hasAttendance
        ? _buildAttendanceCard(appColors)
        : null;

    // Ikkala moduli bo'lsa — Row, bitta bo'lsa — to'liq kenglikda
    if (deliveryWidget != null && attendanceWidget != null) {
      return Row(
        children: [
          Expanded(child: deliveryWidget),
          const SizedBox(width: AppSpacing.sm),
          Expanded(child: attendanceWidget),
        ],
      );
    }

    return deliveryWidget ?? attendanceWidget ?? const SizedBox.shrink();
  }

  Widget _buildAttendanceCard(AppColors appColors) {
    final (icon, color, title) = switch (attendanceState) {
      AttendanceCheckedIn() => (
          Icons.work_rounded,
          appColors.success,
          'Ish jarayonda',
        ),
      AttendanceCheckedOut() => (
          Icons.work_off_rounded,
          appColors.warning,
          'Ish tugadi',
        ),
      AttendanceIdle() => (
          Icons.fingerprint,
          appColors.info,
          'Qayd etilmagan',
        ),
      _ => (Icons.work_outline, appColors.warning, 'Davomat'),
    };

    return StatCard(
      icon: icon,
      label: 'Davomat',
      value: title,
      accentColor: color,
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

/// Kuryer tezkor harakatlar gridi.
class _CourierQuickActions extends StatelessWidget {
  const _CourierQuickActions({
    required this.hasDelivery,
    required this.hasAttendance,
    required this.hasMarketplace,
  });

  final bool hasDelivery;
  final bool hasAttendance;
  final bool hasMarketplace;

  @override
  Widget build(BuildContext context) {
    final actions = <_QuickActionData>[
      if (hasDelivery)
        _QuickActionData(
          icon: Icons.local_shipping_rounded,
          label: 'Yetkazishlar',
          route: '/home/deliveries',
        ),
      if (hasMarketplace)
        _QuickActionData(
          icon: Icons.storefront_rounded,
          label: 'MP Yetkazish',
          route: '/home/courier/mp-deliveries',
        ),
      if (hasAttendance)
        _QuickActionData(
          icon: Icons.fingerprint,
          label: 'Davomat',
          route: '/home/attendance',
        ),
    ];

    if (actions.isEmpty) {
      return EmptyState(
        icon: Icons.widgets_outlined,
        title: 'Modullar yo\'q',
        message: 'Administrator tomonidan modullar faollashtirilmagan.',
        compact: true,
      );
    }

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
