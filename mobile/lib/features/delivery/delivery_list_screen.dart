import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/app_spacing.dart';
import '../../core/widgets/widgets.dart';
import '../../data/local/database.dart';
import 'delivery_providers.dart';

/// Yetkazishlar ro'yxati ekrani — kuryerga tayinlangan yetkazishlar.
///
/// Ma'lumotlar lokal Drift bazasidan (offline-first).
/// Holat badge: assigned/started/delivering/delivered/failed.
class DeliveryListScreen extends ConsumerWidget {
  const DeliveryListScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final deliveriesAsync = ref.watch(deliveriesStreamProvider);
    final cs = Theme.of(context).colorScheme;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Yetkazishlar'),
        actions: [
          deliveriesAsync.when(
            data: (list) {
              final active =
                  list.where((d) => !_isTerminal(d.status)).length;
              if (active == 0) return const SizedBox.shrink();
              return Padding(
                padding: const EdgeInsets.all(AppSpacing.md),
                child: Badge(
                  label: Text('$active'),
                  child: const Icon(Icons.local_shipping_outlined),
                ),
              );
            },
            loading: () => const SizedBox.shrink(),
            error: (_, __) => const SizedBox.shrink(),
          ),
        ],
      ),
      body: deliveriesAsync.when(
        data: (deliveries) {
          if (deliveries.isEmpty) {
            return const EmptyState(
              icon: Icons.local_shipping_outlined,
              title: "Tayinlangan yetkazish yo'q",
              message: 'Yetkazishlar sync orqali yuklanadi.',
            );
          }
          return ListView.separated(
            padding: const EdgeInsets.all(AppSpacing.lg),
            itemCount: deliveries.length,
            separatorBuilder: (_, __) =>
                const SizedBox(height: AppSpacing.sm),
            itemBuilder: (context, index) {
              return _DeliveryCard(
                delivery: deliveries[index],
                onTap: () => context.push(
                  '/home/deliveries/${deliveries[index].id}',
                ),
              );
            },
          );
        },
        loading: () => Center(
          child: CircularProgressIndicator(color: cs.primary),
        ),
        error: (e, _) => EmptyState(
          icon: Icons.error_outline,
          title: 'Xatolik yuz berdi',
          message: e.toString(),
        ),
      ),
    );
  }

  bool _isTerminal(String status) =>
      status == 'delivered' || status == 'failed';
}

class _DeliveryCard extends StatelessWidget {
  const _DeliveryCard({
    required this.delivery,
    required this.onTap,
  });

  final Delivery delivery;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    final statusVariant = _statusVariant(delivery.status);
    final statusLabel = _statusLabel(delivery.status);
    final statusIcon = _statusIcon(delivery.status);

    return AppCard(
      onTap: onTap,
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Sarlavha satri: order ID + badge
          Row(
            children: [
              Container(
                width: AppSpacing.iconLg + AppSpacing.md,
                height: AppSpacing.iconLg + AppSpacing.md,
                decoration: BoxDecoration(
                  color: cs.primaryContainer,
                  borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
                ),
                child: Icon(statusIcon,
                    size: AppSpacing.iconSm, color: cs.primary),
              ),
              const SizedBox(width: AppSpacing.md),
              Expanded(
                child: Text(
                  'Buyurtma: ${delivery.orderId.substring(0, 8)}...',
                  style: tt.titleSmall?.copyWith(fontWeight: FontWeight.w600),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              StatusBadge(status: statusLabel, variant: statusVariant),
            ],
          ),

          if (delivery.address != null || delivery.customerName != null) ...[
            const SizedBox(height: AppSpacing.md),
            if (delivery.address != null)
              _InfoLine(
                icon: Icons.location_on_outlined,
                text: delivery.address!,
              ),
            if (delivery.customerName != null) ...[
              const SizedBox(height: AppSpacing.xs),
              _InfoLine(
                icon: Icons.person_outline,
                text: delivery.customerName!,
              ),
            ],
          ],

          const SizedBox(height: AppSpacing.md),
          Divider(
            height: 1,
            color: cs.outlineVariant,
          ),
          const SizedBox(height: AppSpacing.sm),

          // Pastki satr: sana + sync holat
          Row(
            children: [
              Icon(Icons.schedule_outlined,
                  size: AppSpacing.iconXs,
                  color: cs.onSurfaceVariant),
              const SizedBox(width: AppSpacing.xs),
              Text(
                _fmtDate(delivery.assignedAt ?? delivery.createdAt),
                style: tt.bodySmall?.copyWith(color: cs.onSurfaceVariant),
              ),
              const Spacer(),
              if (delivery.syncStatus == 'pending')
                Icon(Icons.sync_outlined,
                    size: AppSpacing.iconXs,
                    color: Theme.of(context).colorScheme.tertiary),
              if (delivery.syncStatus == 'conflict')
                Icon(Icons.warning_amber_outlined,
                    size: AppSpacing.iconXs,
                    color: Theme.of(context).colorScheme.error),
              const SizedBox(width: AppSpacing.xs),
              Icon(Icons.chevron_right,
                  size: AppSpacing.iconSm,
                  color: cs.onSurfaceVariant),
            ],
          ),
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

  String _fmtDate(DateTime dt) =>
      '${dt.day.toString().padLeft(2, '0')}.${dt.month.toString().padLeft(2, '0')} '
      '${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
}

class _InfoLine extends StatelessWidget {
  const _InfoLine({required this.icon, required this.text});
  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    return Row(
      children: [
        Icon(icon, size: AppSpacing.iconXs, color: cs.onSurfaceVariant),
        const SizedBox(width: AppSpacing.xs),
        Expanded(
          child: Text(
            text,
            style: tt.bodySmall?.copyWith(color: cs.onSurfaceVariant),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        ),
      ],
    );
  }
}
