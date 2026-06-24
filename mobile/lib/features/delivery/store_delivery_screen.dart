import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/widgets.dart';
import '../../data/local/database.dart';
import '../auth/auth_providers.dart';
import '../auth/auth_repository.dart';
import 'delivery_providers.dart';

/// Do'kon roli uchun o'z yetkazishlarini kuzatish ekrani.
///
/// Do'konga tegishli buyurtmalarning yetkazish holati ko'rsatiladi.
/// Lokal Drift'dan stream orqali (offline-first).
class StoreDeliveryScreen extends ConsumerWidget {
  const StoreDeliveryScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final authState = ref.watch(authNotifierProvider);
    final storeId = switch (authState) {
      AuthStateAuthenticated(:final user) => user.branchId,
      _ => null,
    };

    return Scaffold(
      appBar: AppBar(
        title: const Text('Yetkazishlar'),
        actions: [
          Consumer(builder: (context, ref, _) {
            final showAll = ref.watch(_storeDeliveryShowAllProvider);
            return IconButton(
              icon: Icon(showAll ? Icons.filter_list_off : Icons.filter_list),
              tooltip: showAll ? 'Faqat faollar' : 'Hammasi',
              onPressed: () => ref
                  .read(_storeDeliveryShowAllProvider.notifier)
                  .state = !showAll,
            );
          }),
        ],
      ),
      body: storeId == null
          ? const EmptyState(
              icon: Icons.store_outlined,
              title: "Do'kon ID topilmadi",
              message: "Akkauntga do'kon biriktirilmagan.",
            )
          : _StoreDeliveryBody(storeId: storeId),
    );
  }
}

// ---------------------------------------------------------------------------

final _storeDeliveryShowAllProvider =
    StateProvider.autoDispose<bool>((ref) => false);

// ---------------------------------------------------------------------------

class _StoreDeliveryBody extends ConsumerWidget {
  const _StoreDeliveryBody({required this.storeId});
  final String storeId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final showAll = ref.watch(_storeDeliveryShowAllProvider);

    final deliveriesAsync = showAll
        ? ref.watch(deliveriesStreamProvider)
        : ref.watch(activeDeliveriesStreamProvider);

    return deliveriesAsync.when(
      loading: () => Center(
        child: CircularProgressIndicator(
            color: Theme.of(context).colorScheme.primary),
      ),
      error: (e, _) => EmptyState(
        icon: Icons.error_outline,
        title: 'Xatolik yuz berdi',
        message: e.toString(),
      ),
      data: (deliveries) {
        if (deliveries.isEmpty) {
          return EmptyState(
            icon: Icons.local_shipping_outlined,
            title: showAll
                ? "Hali yetkazishlar yo'q"
                : "Faol yetkazishlar yo'q",
            message: "Buyurtmalar tayinlangach bu yerda ko'rinadi.",
          );
        }
        return RefreshIndicator(
          onRefresh: () async {},
          child: Column(
            children: [
              _SummaryBanner(deliveries: deliveries),
              Expanded(
                child: ListView.separated(
                  padding: const EdgeInsets.fromLTRB(
                      AppSpacing.lg,
                      AppSpacing.md,
                      AppSpacing.lg,
                      AppSpacing.xl),
                  itemCount: deliveries.length,
                  separatorBuilder: (_, __) =>
                      const SizedBox(height: AppSpacing.sm),
                  itemBuilder: (context, i) =>
                      _DeliveryCard(delivery: deliveries[i]),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

// ---------------------------------------------------------------------------

class _SummaryBanner extends StatelessWidget {
  const _SummaryBanner({required this.deliveries});
  final List<Delivery> deliveries;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final appColors = AppTheme.colorsOf(context);
    final delivering =
        deliveries.where((d) => d.status == 'delivering').length;
    final delivered =
        deliveries.where((d) => d.status == 'delivered').length;
    final failed = deliveries.where((d) => d.status == 'failed').length;

    return Container(
      padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.lg, vertical: AppSpacing.md),
      decoration: BoxDecoration(
        color: cs.surface,
        border: Border(
          bottom: BorderSide(color: cs.outlineVariant),
        ),
      ),
      child: Row(
        children: [
          _StatChip(
            label: 'Yetkazilmoqda',
            value: delivering,
            color: cs.secondary,
          ),
          const Spacer(),
          _StatChip(
            label: 'Yetkazildi',
            value: delivered,
            color: appColors.success,
          ),
          const Spacer(),
          _StatChip(
            label: 'Muvaffaqiyatsiz',
            value: failed,
            color: appColors.danger,
          ),
        ],
      ),
    );
  }
}

class _StatChip extends StatelessWidget {
  const _StatChip({
    required this.label,
    required this.value,
    required this.color,
  });

  final String label;
  final int value;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final tt = Theme.of(context).textTheme;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          '$value',
          style: tt.headlineSmall?.copyWith(
            fontWeight: FontWeight.w700,
            color: color,
            letterSpacing: -0.5,
          ),
        ),
        Text(
          label,
          style: tt.labelSmall?.copyWith(
              color: Theme.of(context).colorScheme.onSurfaceVariant),
        ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------

class _DeliveryCard extends StatelessWidget {
  const _DeliveryCard({required this.delivery});
  final Delivery delivery;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    final statusVariant = _statusVariant(delivery.status);
    final statusLabel = _statusLabel(delivery.status);
    final statusIcon = _statusIcon(delivery.status);

    final iconBgColor = switch (statusVariant) {
      StatusVariant.success =>
        AppTheme.colorsOf(context).successContainer.withValues(alpha: 0.5),
      StatusVariant.warning =>
        AppTheme.colorsOf(context).warningContainer.withValues(alpha: 0.5),
      StatusVariant.danger =>
        AppTheme.colorsOf(context).dangerContainer.withValues(alpha: 0.5),
      StatusVariant.info =>
        AppTheme.colorsOf(context).infoContainer.withValues(alpha: 0.5),
      _ => cs.surfaceContainerHighest,
    };
    final iconColor = switch (statusVariant) {
      StatusVariant.success => AppTheme.colorsOf(context).success,
      StatusVariant.warning => AppTheme.colorsOf(context).warning,
      StatusVariant.danger => AppTheme.colorsOf(context).danger,
      StatusVariant.info => AppTheme.colorsOf(context).info,
      _ => cs.onSurfaceVariant,
    };

    return AppCard(
      onTap: () => context.push('/home/deliveries/${delivery.id}'),
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Row(
        children: [
          Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              color: iconBgColor,
              borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
            ),
            child: Icon(statusIcon, color: iconColor, size: AppSpacing.iconSm),
          ),
          const SizedBox(width: AppSpacing.md),

          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        'Buyurtma: ${delivery.orderId.substring(0, 8)}...',
                        style: tt.titleSmall?.copyWith(
                            fontWeight: FontWeight.w600),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    const SizedBox(width: AppSpacing.xs),
                    StatusBadge(
                        status: statusLabel, variant: statusVariant),
                  ],
                ),
                if (delivery.address != null) ...[
                  const SizedBox(height: AppSpacing.xs),
                  Row(
                    children: [
                      Icon(Icons.location_on_outlined,
                          size: 12, color: cs.onSurfaceVariant),
                      const SizedBox(width: AppSpacing.xs),
                      Expanded(
                        child: Text(
                          delivery.address!,
                          style: tt.bodySmall
                              ?.copyWith(color: cs.onSurfaceVariant),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ),
                ],
                if (delivery.customerName != null) ...[
                  const SizedBox(height: 2),
                  Row(
                    children: [
                      Icon(Icons.person_outline,
                          size: 12, color: cs.onSurfaceVariant),
                      const SizedBox(width: AppSpacing.xs),
                      Text(
                        delivery.customerName!,
                        style: tt.bodySmall
                            ?.copyWith(color: cs.onSurfaceVariant),
                      ),
                    ],
                  ),
                ],
              ],
            ),
          ),

          Icon(Icons.chevron_right,
              color: cs.onSurfaceVariant, size: AppSpacing.iconSm),
        ],
      ),
    );
  }

  StatusVariant _statusVariant(String status) => switch (status) {
        'assigned' => StatusVariant.info,
        'started' => StatusVariant.warning,
        'delivering' => StatusVariant.warning,
        'delivered' => StatusVariant.success,
        'failed' => StatusVariant.danger,
        _ => StatusVariant.neutral,
      };

  String _statusLabel(String status) => switch (status) {
        'assigned' => 'Tayinlangan',
        'started' => 'Boshlandi',
        'delivering' => 'Yetkazilmoqda',
        'delivered' => 'Yetkazildi',
        'failed' => 'Muvaffaqiyatsiz',
        _ => status,
      };

  IconData _statusIcon(String status) => switch (status) {
        'assigned' => Icons.assignment_outlined,
        'started' => Icons.directions_run_outlined,
        'delivering' => Icons.local_shipping_outlined,
        'delivered' => Icons.check_circle_outline,
        'failed' => Icons.cancel_outlined,
        _ => Icons.help_outline,
      };
}
