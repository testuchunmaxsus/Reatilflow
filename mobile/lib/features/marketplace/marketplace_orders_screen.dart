import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/app_card.dart';
import '../../core/widgets/empty_state.dart';
import '../../core/widgets/status_badge.dart';
import 'marketplace_models.dart';
import 'marketplace_providers.dart';

/// Mening buyurtmalarim (outgoing) ekrani.
///
/// GET /marketplace/orders/outgoing — holat bilan.
class MarketplaceOrdersScreen extends ConsumerWidget {
  const MarketplaceOrdersScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final ordersState = ref.watch(outgoingOrdersProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Buyurtmalarim'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            tooltip: 'Yangilash',
            onPressed: () =>
                ref.read(outgoingOrdersProvider.notifier).load(),
          ),
        ],
      ),
      body: switch (ordersState) {
        OutgoingOrdersLoading() => _OrdersLoadingSkeleton(),
        OutgoingOrdersError(:final message) => EmptyState(
            icon: Icons.error_outline,
            title: 'Xatolik yuz berdi',
            message: message,
            iconColor: AppTheme.colorsOf(context).danger,
            actionLabel: 'Qayta urinish',
            onAction: () =>
                ref.read(outgoingOrdersProvider.notifier).load(),
          ),
        OutgoingOrdersLoaded(orders: final orders)
            when orders.isEmpty =>
          EmptyState(
            icon: Icons.receipt_long_outlined,
            title: 'Buyurtmalar yo\'q',
            message:
                'Marketplacega o\'tib birinchi buyurtmangizni bering',
            actionLabel: 'Marketplacega o\'tish',
            onAction: () => context.go('/home/marketplace'),
          ),
        OutgoingOrdersLoaded(:final orders) => RefreshIndicator(
            onRefresh: () =>
                ref.read(outgoingOrdersProvider.notifier).load(),
            child: ListView.builder(
              padding: const EdgeInsets.fromLTRB(
                AppSpacing.lg,
                AppSpacing.md,
                AppSpacing.lg,
                AppSpacing.xxxl,
              ),
              itemCount: orders.length,
              itemBuilder: (context, i) =>
                  _OrderCard(order: orders[i]),
            ),
          ),
      },
    );
  }
}

class _OrderCard extends StatelessWidget {
  const _OrderCard({required this.order});
  final MarketplaceOrder order;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    final appColors = AppTheme.colorsOf(context);
    final (statusColor, statusIcon) = order.status.style;

    // StatusVariant aniqlash
    final variant = switch (order.status) {
      MarketplaceOrderStatus.accepted => StatusVariant.success,
      MarketplaceOrderStatus.delivered => StatusVariant.success,
      MarketplaceOrderStatus.confirmed => StatusVariant.info,
      MarketplaceOrderStatus.delivering => StatusVariant.info,
      MarketplaceOrderStatus.pending => StatusVariant.warning,
      MarketplaceOrderStatus.cancelled => StatusVariant.danger,
    };

    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: AppCard(
        padding: const EdgeInsets.all(AppSpacing.md),
        onTap: () => context
            .go('/home/marketplace/orders/${order.id}'),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Holat + ID
            Row(
              children: [
                StatusBadge(
                  status: order.status.label,
                  variant: variant,
                  icon: statusIcon,
                ),
                const Spacer(),
                Text(
                  '#${order.id.substring(0, 8)}',
                  style: tt.labelSmall?.copyWith(
                    color: cs.onSurfaceVariant,
                    fontFamily: 'monospace',
                  ),
                ),
              ],
            ),

            const SizedBox(height: AppSpacing.md),

            // Supplier nomi
            Row(
              children: [
                Container(
                  width: 32,
                  height: 32,
                  decoration: BoxDecoration(
                    color: cs.primaryContainer,
                    borderRadius:
                        BorderRadius.circular(AppSpacing.radiusSm),
                  ),
                  child: Icon(Icons.storefront,
                      size: AppSpacing.iconSm, color: cs.primary),
                ),
                const SizedBox(width: AppSpacing.sm),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        order.supplierEnterpriseName,
                        style: tt.titleSmall?.copyWith(
                          fontWeight: FontWeight.w600,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                      // Mahsulotlar ro'yxati (qisqacha)
                      Text(
                        order.lines
                            .take(3)
                            .map((l) =>
                                '${l.productName} x${l.qty.toStringAsFixed(l.qty % 1 == 0 ? 0 : 1)}')
                            .join(', '),
                        style: tt.bodySmall?.copyWith(
                          color: cs.onSurfaceVariant,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                  ),
                ),
              ],
            ),

            if (order.lines.length > 3) ...[
              const SizedBox(height: AppSpacing.xs),
              Padding(
                padding: const EdgeInsets.only(left: 40),
                child: Text(
                  '+${order.lines.length - 3} ta boshqa mahsulot',
                  style: tt.labelSmall?.copyWith(
                    color: cs.onSurfaceVariant,
                  ),
                ),
              ),
            ],

            const SizedBox(height: AppSpacing.md),
            Divider(color: cs.outlineVariant, height: 1),
            const SizedBox(height: AppSpacing.sm),

            // Sana + qabul qilish tugmasi
            Row(
              children: [
                Icon(Icons.schedule,
                    size: 12,
                    color: cs.onSurfaceVariant),
                const SizedBox(width: AppSpacing.xs),
                Text(
                  _fmtDate(order.createdAt),
                  style: tt.labelSmall?.copyWith(
                    color: cs.onSurfaceVariant,
                  ),
                ),
                if (order.totalAmount != null) ...[
                  const SizedBox(width: AppSpacing.sm),
                  Container(
                    width: 4,
                    height: 4,
                    decoration: BoxDecoration(
                      color: cs.outlineVariant,
                      shape: BoxShape.circle,
                    ),
                  ),
                  const SizedBox(width: AppSpacing.sm),
                  Text(
                    _fmtAmount(order.totalAmount!),
                    style: tt.labelSmall?.copyWith(
                      color: cs.onSurface,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
                const Spacer(),

                // delivered holat — qabul qilish tugmasi
                if (order.canAccept)
                  FilledButton.icon(
                    style: FilledButton.styleFrom(
                      backgroundColor: appColors.success,
                      foregroundColor: appColors.onSuccess,
                      padding: const EdgeInsets.symmetric(
                          horizontal: AppSpacing.md,
                          vertical: AppSpacing.xs),
                      minimumSize: Size.zero,
                      tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                    ),
                    onPressed: () => context.go(
                      '/home/marketplace/orders/${order.id}/accept',
                    ),
                    icon: const Icon(Icons.check_circle_outline,
                        size: AppSpacing.iconSm),
                    label: const Text('Qabul qilish',
                        style: TextStyle(fontWeight: FontWeight.w600)),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  String _fmtDate(DateTime dt) {
    String pad2(int n) => n.toString().padLeft(2, '0');
    return '${pad2(dt.day)}.${pad2(dt.month)}.${dt.year} '
        '${pad2(dt.hour)}:${pad2(dt.minute)}';
  }

  String _fmtAmount(double v) {
    if (v >= 1000000) return '${(v / 1000000).toStringAsFixed(1)} mln so\'m';
    if (v >= 1000) return '${(v / 1000).toStringAsFixed(0)} ming so\'m';
    return '${v.toStringAsFixed(0)} so\'m';
  }
}

// ---------------------------------------------------------------------------
// Loading skeleton

class _OrdersLoadingSkeleton extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final base = cs.surfaceContainerHighest;

    Widget block(double w, double h) => Container(
          width: w,
          height: h,
          decoration: BoxDecoration(
            color: base,
            borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
          ),
        );

    return ListView.builder(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.lg,
        AppSpacing.md,
        AppSpacing.lg,
        AppSpacing.sm,
      ),
      itemCount: 4,
      itemBuilder: (_, __) => Padding(
        padding: const EdgeInsets.only(bottom: AppSpacing.sm),
        child: AppCard(
          padding: const EdgeInsets.all(AppSpacing.md),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  block(80, 24),
                  const Spacer(),
                  block(70, 14),
                ],
              ),
              const SizedBox(height: AppSpacing.md),
              Row(
                children: [
                  block(32, 32),
                  const SizedBox(width: AppSpacing.sm),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        block(140, 16),
                        const SizedBox(height: AppSpacing.xs),
                        block(200, 12),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: AppSpacing.md),
              Divider(color: cs.outlineVariant, height: 1),
              const SizedBox(height: AppSpacing.sm),
              Row(
                children: [
                  block(100, 12),
                  const Spacer(),
                  block(90, 30),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
