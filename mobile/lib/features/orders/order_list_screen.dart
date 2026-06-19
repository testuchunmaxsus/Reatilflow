import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../data/local/database.dart';
import 'orders_providers.dart';

/// Buyurtmalar ro'yxati ekrani — lokal Drift'dan (offline).
/// Sync holati (pending/synced) ko'rsatiladi.
class OrderListScreen extends ConsumerWidget {
  const OrderListScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final ordersAsync = ref.watch(ordersStreamProvider);

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
            return const Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.receipt_long_outlined,
                      size: 64, color: Colors.grey),
                  SizedBox(height: 12),
                  Text('Buyurtmalar yo\'q',
                      style: TextStyle(color: Colors.grey)),
                  SizedBox(height: 6),
                  Text(
                    'Yangi buyurtma yarating',
                    style: TextStyle(color: Colors.grey, fontSize: 12),
                  ),
                ],
              ),
            );
          }
          return ListView.builder(
            itemCount: orders.length,
            itemBuilder: (ctx, i) => _OrderCard(order: orders[i]),
          );
        },
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Xatolik: $e')),
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
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: _statusColor(order.syncStatus).withValues(alpha:0.1),
          child: Icon(
            _statusIcon(order.status),
            color: _statusColor(order.syncStatus),
          ),
        ),
        title: Text(
          'Buyurtma ${order.id.substring(0, 8)}...',
          style: const TextStyle(fontWeight: FontWeight.w600),
        ),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Do\'kon: ${order.storeId.substring(0, 8)}...',
              style: const TextStyle(fontSize: 12),
            ),
            Text(
              _formatDate(order.createdAt),
              style: const TextStyle(fontSize: 11, color: Colors.grey),
            ),
          ],
        ),
        trailing: _SyncBadge(syncStatus: order.syncStatus),
        isThreeLine: true,
      ),
    );
  }

  Color _statusColor(String syncStatus) {
    return switch (syncStatus) {
      'synced' => Colors.green,
      'pending' => Colors.orange,
      'conflict' => Colors.red,
      'error' => Colors.red,
      _ => Colors.grey,
    };
  }

  IconData _statusIcon(String status) {
    return switch (status) {
      'confirmed' => Icons.check_circle_outline,
      'draft' => Icons.drafts_outlined,
      'packed' => Icons.inventory_outlined,
      'delivering' => Icons.local_shipping_outlined,
      'delivered' => Icons.done_all,
      'canceled' => Icons.cancel_outlined,
      _ => Icons.receipt_long_outlined,
    };
  }

  String _formatDate(DateTime dt) {
    return '${dt.day.toString().padLeft(2, '0')}.'
        '${dt.month.toString().padLeft(2, '0')}.'
        '${dt.year} '
        '${dt.hour.toString().padLeft(2, '0')}:'
        '${dt.minute.toString().padLeft(2, '0')}';
  }
}

class _SyncBadge extends StatelessWidget {
  const _SyncBadge({required this.syncStatus});
  final String syncStatus;

  @override
  Widget build(BuildContext context) {
    final (label, color) = switch (syncStatus) {
      'synced' => ('Yuborildi', Colors.green),
      'pending' => ('Kutilmoqda', Colors.orange),
      'conflict' => ('Ziddiyat', Colors.red),
      'error' => ('Xatolik', Colors.red),
      _ => (syncStatus, Colors.grey),
    };

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha:0.1),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withValues(alpha:0.4)),
      ),
      child: Text(
        label,
        style: TextStyle(
            color: color, fontSize: 11, fontWeight: FontWeight.w600),
      ),
    );
  }
}
