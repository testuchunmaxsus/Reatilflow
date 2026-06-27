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
import '../../core/widgets/status_badge.dart';
import '../../data/sync/sync_notifier.dart';
import '../attendance/attendance_providers.dart';
import '../auth/auth_providers.dart';
import '../auth/auth_repository.dart';
import '../enterprise/enterprise_providers.dart';
import '../home/sync_providers.dart';
import '../orders/orders_providers.dart';

/// Agent uchun bosh ekran — dashboard.
///
/// Ko'rsatiladi:
/// - DashboardHeader (salom, ism, rol)
/// - Davomat holati (StatCard)
/// - Sync holati (AppCard)
/// - Tezkor harakatlar grid
/// - So'nggi buyurtmalar
class AgentDashboard extends ConsumerWidget {
  const AgentDashboard({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final authState = ref.watch(authNotifierProvider);
    final user = switch (authState) {
      AuthStateAuthenticated(:final user) => user,
      _ => null,
    };

    final syncState = ref.watch(syncNotifierProvider);
    final attendanceState = ref.watch(attendanceNotifierProvider);

    final initials = user != null
        ? user.fullName
            .trim()
            .split(' ')
            .take(2)
            .map((w) => w.isNotEmpty ? w[0] : '')
            .join()
            .toUpperCase()
        : 'AG';

    return SingleChildScrollView(
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header
          DashboardHeader(
            greeting: 'Salom,',
            name: user?.fullName ?? 'Agent',
            subtitle: _formattedDate(),
            role: 'AGENT',
            avatarInitials: initials,
            trailing: _SyncStatusButton(syncState: syncState, ref: ref),
          ),

          const SizedBox(height: AppSpacing.lg),

          // Davomat stat kartasi
          _AttendanceStatRow(attendanceState: attendanceState),

          const SizedBox(height: AppSpacing.lg),

          // Tezkor harakatlar
          SectionHeader(
            title: 'Tezkor harakatlar',
            subtitle: 'Eng ko\'p ishlatiladigan funksiyalar',
          ),
          const SizedBox(height: AppSpacing.sm),
          _AgentQuickActions(),

          const SizedBox(height: AppSpacing.lg),

          // So'nggi buyurtmalar
          SectionHeader(
            title: 'So\'nggi buyurtmalar',
            actionLabel: 'Barchasi',
            onAction: () => context.push('/home/orders'),
          ),
          const SizedBox(height: AppSpacing.sm),

          _RecentOrders(),

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

/// Davomat holati — bir yoki ikki StatCard.
class _AttendanceStatRow extends StatelessWidget {
  const _AttendanceStatRow({required this.attendanceState});
  final AttendanceState attendanceState;

  @override
  Widget build(BuildContext context) {
    final appColors = AppTheme.colorsOf(context);

    final (icon, color, title, subtitle) = switch (attendanceState) {
      AttendanceCheckedIn(:final record) => (
          Icons.work_rounded,
          appColors.success,
          'Ish jarayonda',
          'Kirish: ${_fmt(record.checkInAt)}',
        ),
      AttendanceCheckedOut(:final record) => (
          Icons.work_off_rounded,
          appColors.warning,
          'Ish tugadi',
          'Chiqish: ${_fmt(record.checkOutAt!)}',
        ),
      AttendanceIdle() => (
          Icons.fingerprint,
          appColors.info,
          'Qayd etilmagan',
          'Boshlash uchun bosing',
        ),
      _ => (Icons.work_outline, appColors.warning, 'Davomat', ''),
    };

    return StatCard(
      icon: icon,
      label: 'Davomat holati',
      value: title,
      subtitle: subtitle.isNotEmpty ? subtitle : null,
      accentColor: color,
      onTap: () => Navigator.of(context).pushNamed('/home/attendance'),
    );
  }

  String _fmt(DateTime dt) =>
      '${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
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

/// Tezkor harakatlar grid — enabled_modules ga qarab.
class _AgentQuickActions extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final hasCatalog = ref.watch(moduleEnabledProvider('catalog'));
    final hasOrders = ref.watch(moduleEnabledProvider('orders'));
    final hasAttendance = ref.watch(moduleEnabledProvider('attendance'));
    final hasMarketplace = ref.watch(moduleEnabledProvider('marketplace'));

    final actions = <_QuickActionData>[
      if (hasOrders)
        _QuickActionData(
          icon: Icons.add_shopping_cart_rounded,
          label: 'Buyurtma',
          route: '/home/orders/create',
        ),
      _QuickActionData(
        icon: Icons.store_rounded,
        label: "Do'konlar",
        route: '/home/stores',
      ),
      if (hasCatalog)
        _QuickActionData(
          icon: Icons.inventory_2_rounded,
          label: 'Katalog',
          route: '/home/catalog',
        ),
      if (hasMarketplace)
        _QuickActionData(
          icon: Icons.storefront_rounded,
          label: 'Marketplace',
          route: '/home/marketplace',
        ),
      if (hasAttendance)
        _QuickActionData(
          icon: Icons.fingerprint,
          label: 'Davomat',
          route: '/home/attendance',
        ),
      _QuickActionData(
        icon: Icons.manage_accounts_rounded,
        label: 'Kabinet',
        route: '/home/agent/cabinet',
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
                onTap: () => context.push(a.route),
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

/// Tezkor amal kartasi — tema renklaridan foydalanadi.
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

/// So'nggi buyurtmalar ro'yxati.
class _RecentOrders extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final ordersAsync = ref.watch(ordersStreamProvider);

    return ordersAsync.when(
      data: (orders) {
        final recent = orders.take(3).toList();
        if (recent.isEmpty) {
          return EmptyState(
            icon: Icons.receipt_long_outlined,
            title: 'Buyurtmalar yo\'q',
            message: 'Yangi buyurtma yaratish uchun + tugmasini bosing.',
            compact: true,
          );
        }
        return Column(
          children: recent
              .map((o) => _OrderTile(order: o))
              .toList(),
        );
      },
      loading: () => _OrdersSkeletonList(),
      error: (e, _) => EmptyState(
        icon: Icons.error_outline,
        title: 'Yuklanmadi',
        message: e.toString(),
        compact: true,
      ),
    );
  }
}

class _OrderTile extends StatelessWidget {
  const _OrderTile({required this.order});
  final dynamic order;

  @override
  Widget build(BuildContext context) {
    final tt = Theme.of(context).textTheme;
    final cs = Theme.of(context).colorScheme;
    final isSynced = order.syncStatus == 'synced';

    return AppCard(
      margin: const EdgeInsets.only(bottom: AppSpacing.sm),
      onTap: () => context.push('/home/orders'),
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.sm,
      ),
      child: Row(
        children: [
          Container(
            width: 36,
            height: 36,
            decoration: BoxDecoration(
              color: isSynced
                  ? AppTheme.colorsOf(context).successContainer.withValues(alpha: 0.5)
                  : AppTheme.colorsOf(context).warningContainer.withValues(alpha: 0.5),
              borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
            ),
            child: Icon(
              isSynced
                  ? Icons.check_circle_outline
                  : Icons.pending_outlined,
              color: isSynced
                  ? AppTheme.colorsOf(context).success
                  : AppTheme.colorsOf(context).warning,
              size: AppSpacing.iconSm,
            ),
          ),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '#${order.id.substring(0, 8)}',
                  style: tt.bodyMedium?.copyWith(
                    fontWeight: FontWeight.w600,
                    color: cs.onSurface,
                  ),
                ),
                Text(
                  _fmtDate(order.createdAt as DateTime),
                  style: tt.bodySmall?.copyWith(color: cs.onSurfaceVariant),
                ),
              ],
            ),
          ),
          StatusBadge(
            status: isSynced ? 'Yuborildi' : 'Kutilmoqda',
            variant: isSynced ? StatusVariant.success : StatusVariant.warning,
            size: StatusBadgeSize.small,
          ),
        ],
      ),
    );
  }

  String _fmtDate(DateTime dt) =>
      '${dt.day.toString().padLeft(2, '0')}.${dt.month.toString().padLeft(2, '0')} '
      '${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
}

class _OrdersSkeletonList extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final base = cs.surfaceContainerHighest;

    return Column(
      children: List.generate(
        3,
        (_) => AppCard(
          margin: const EdgeInsets.only(bottom: AppSpacing.sm),
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.md,
            vertical: AppSpacing.sm,
          ),
          child: Row(
            children: [
              Container(
                width: 36,
                height: 36,
                decoration: BoxDecoration(
                  color: base,
                  borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
                ),
              ),
              const SizedBox(width: AppSpacing.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Container(
                      width: 100,
                      height: 14,
                      decoration: BoxDecoration(
                        color: base,
                        borderRadius: BorderRadius.circular(AppSpacing.radiusXs),
                      ),
                    ),
                    const SizedBox(height: AppSpacing.xs),
                    Container(
                      width: 70,
                      height: 11,
                      decoration: BoxDecoration(
                        color: base.withValues(alpha: 0.6),
                        borderRadius: BorderRadius.circular(AppSpacing.radiusXs),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
