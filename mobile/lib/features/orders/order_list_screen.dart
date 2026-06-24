import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/app_spacing.dart';
import '../../core/widgets/widgets.dart';
import '../../data/local/database.dart';
import 'orders_providers.dart';

/// Buyurtmalar ro'yxati ekrani — lokal Drift'dan (offline).
/// Sync holati (pending/synced) ko'rsatiladi.
class OrderListScreen extends ConsumerWidget {
  const OrderListScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final ordersAsync = ref.watch(ordersStreamProvider);
    final cs = Theme.of(context).colorScheme;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Buyurtmalar'),
        actions: [
          IconButton(
            icon: const Icon(Icons.add),
            tooltip: 'Yangi buyurtma',
            onPressed: () => context.push('/home/orders/create'),
          ),
        ],
      ),
      body: ordersAsync.when(
        data: (orders) {
          if (orders.isEmpty) {
            return EmptyState(
              icon: Icons.receipt_long_outlined,
              title: "Buyurtmalar yo'q",
              message: 'Yangi buyurtma yarating',
              actionLabel: 'Buyurtma yaratish',
              onAction: () => context.push('/home/orders/create'),
            );
          }
          return ListView.separated(
            padding: const EdgeInsets.all(AppSpacing.lg),
            itemCount: orders.length,
            separatorBuilder: (_, __) =>
                const SizedBox(height: AppSpacing.sm),
            itemBuilder: (ctx, i) => _OrderCard(order: orders[i]),
          );
        },
        loading: () =>
            Center(child: CircularProgressIndicator(color: cs.primary)),
        error: (e, _) => EmptyState(
          icon: Icons.error_outline,
          title: 'Xatolik yuz berdi',
          message: e.toString(),
        ),
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => context.push('/home/orders/create'),
        icon: const Icon(Icons.add),
        label: const Text('Buyurtma'),
      ),
    );
  }
}

class _OrderCard extends StatelessWidget {
  const _OrderCard({required this.order});
  final Order order;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    final syncVariant = _syncVariant(order.syncStatus);

    return AppCard(
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Row(
        children: [
          // Status ikon
          Container(
            width: 48,
            height: 48,
            decoration: BoxDecoration(
              color: cs.primaryContainer,
              borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
            ),
            child: Icon(
              _statusIcon(order.status),
              color: cs.primary,
              size: AppSpacing.iconMd,
            ),
          ),
          const SizedBox(width: AppSpacing.lg),

          // Matn
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Buyurtma ${order.id.substring(0, 8)}...',
                  style: tt.titleSmall?.copyWith(fontWeight: FontWeight.w600),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: AppSpacing.xs),
                Text(
                  "Do'kon: ${order.storeId.substring(0, 8)}...",
                  style: tt.bodySmall?.copyWith(color: cs.onSurfaceVariant),
                ),
                Text(
                  _formatDate(order.createdAt),
                  style: tt.labelSmall?.copyWith(color: cs.onSurfaceVariant),
                ),
              ],
            ),
          ),

          const SizedBox(width: AppSpacing.sm),

          // Sync badge
          StatusBadge(
            status: _syncLabel(order.syncStatus),
            variant: syncVariant,
          ),
        ],
      ),
    );
  }

  StatusVariant _syncVariant(String syncStatus) => switch (syncStatus) {
        'synced' => StatusVariant.success,
        'pending' => StatusVariant.warning,
        'conflict' => StatusVariant.danger,
        'error' => StatusVariant.danger,
        _ => StatusVariant.neutral,
      };

  String _syncLabel(String syncStatus) => switch (syncStatus) {
        'synced' => 'Yuborildi',
        'pending' => 'Kutilmoqda',
        'conflict' => 'Ziddiyat',
        'error' => 'Xatolik',
        _ => syncStatus,
      };

  IconData _statusIcon(String status) => switch (status) {
        'confirmed' => Icons.check_circle_outline,
        'draft' => Icons.drafts_outlined,
        'packed' => Icons.inventory_outlined,
        'delivering' => Icons.local_shipping_outlined,
        'delivered' => Icons.done_all,
        'canceled' => Icons.cancel_outlined,
        _ => Icons.receipt_long_outlined,
      };

  String _formatDate(DateTime dt) =>
      '${dt.day.toString().padLeft(2, '0')}.'
      '${dt.month.toString().padLeft(2, '0')}.'
      '${dt.year} '
      '${dt.hour.toString().padLeft(2, '0')}:'
      '${dt.minute.toString().padLeft(2, '0')}';
}
