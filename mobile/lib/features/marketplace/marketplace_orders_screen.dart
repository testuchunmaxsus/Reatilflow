import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

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
            onPressed: () =>
                ref.read(outgoingOrdersProvider.notifier).load(),
          ),
        ],
      ),
      body: switch (ordersState) {
        OutgoingOrdersLoading() =>
          const Center(child: CircularProgressIndicator()),
        OutgoingOrdersError(:final message) => Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.error_outline,
                    color: Colors.red, size: 40),
                const SizedBox(height: 8),
                Text('Xatolik: $message', textAlign: TextAlign.center),
                const SizedBox(height: 12),
                FilledButton(
                  onPressed: () =>
                      ref.read(outgoingOrdersProvider.notifier).load(),
                  child: const Text('Qayta urinish'),
                ),
              ],
            ),
          ),
        OutgoingOrdersLoaded(orders: final orders) when orders.isEmpty =>
          const _EmptyOrders(),
        OutgoingOrdersLoaded(:final orders) => RefreshIndicator(
            onRefresh: () =>
                ref.read(outgoingOrdersProvider.notifier).load(),
            child: ListView.builder(
              padding: const EdgeInsets.all(12),
              itemCount: orders.length,
              itemBuilder: (context, i) =>
                  _OrderCard(order: orders[i]),
            ),
          ),
      },
    );
  }
}

class _EmptyOrders extends StatelessWidget {
  const _EmptyOrders();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.receipt_long, size: 64, color: Colors.grey.shade300),
          const SizedBox(height: 12),
          Text(
            'Buyurtmalar yo\'q',
            style: Theme.of(context)
                .textTheme
                .titleMedium
                ?.copyWith(color: Colors.grey),
          ),
          const SizedBox(height: 8),
          FilledButton(
            onPressed: () => context.go('/home/marketplace'),
            child: const Text('Marketplacega o\'tish'),
          ),
        ],
      ),
    );
  }
}

class _OrderCard extends StatelessWidget {
  const _OrderCard({required this.order});
  final MarketplaceOrder order;

  @override
  Widget build(BuildContext context) {
    final (statusColor, statusIcon) = order.status.style;

    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: () => context.go('/home/marketplace/orders/${order.id}'),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Holat + ID
              Row(
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 8, vertical: 4),
                    decoration: BoxDecoration(
                      color: statusColor.withValues(alpha: 0.12),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(statusIcon,
                            size: 14, color: statusColor),
                        const SizedBox(width: 4),
                        Text(
                          order.status.label,
                          style: TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w600,
                            color: statusColor,
                          ),
                        ),
                      ],
                    ),
                  ),
                  const Spacer(),
                  Text(
                    '#${order.id.substring(0, 8)}',
                    style: const TextStyle(
                      fontSize: 12,
                      color: Colors.grey,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 8),

              // Supplier nomi
              Row(
                children: [
                  const Icon(Icons.storefront,
                      size: 14, color: Colors.grey),
                  const SizedBox(width: 4),
                  Expanded(
                    child: Text(
                      order.supplierEnterpriseName,
                      style: const TextStyle(
                          fontWeight: FontWeight.w500, fontSize: 13),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 6),

              // Mahsulotlar ro'yxati (qisqacha)
              Text(
                order.lines
                    .take(3)
                    .map((l) =>
                        '${l.productName} x${l.qty.toStringAsFixed(l.qty % 1 == 0 ? 0 : 1)}')
                    .join(', '),
                style: TextStyle(
                  fontSize: 12,
                  color: Colors.grey.shade600,
                ),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),

              if (order.lines.length > 3)
                Text(
                  '+${order.lines.length - 3} ta boshqa',
                  style: TextStyle(
                    fontSize: 11,
                    color: Colors.grey.shade500,
                  ),
                ),

              const SizedBox(height: 8),

              // Sana + qabul qilish tugmasi
              Row(
                children: [
                  Icon(Icons.schedule,
                      size: 12, color: Colors.grey.shade500),
                  const SizedBox(width: 4),
                  Text(
                    _fmtDate(order.createdAt),
                    style: TextStyle(
                        fontSize: 11, color: Colors.grey.shade500),
                  ),
                  const Spacer(),

                  // delivered holat — qabul qilish tugmasi
                  if (order.canAccept)
                    FilledButton(
                      style: FilledButton.styleFrom(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 12, vertical: 6),
                        minimumSize: Size.zero,
                        backgroundColor: Colors.green,
                      ),
                      onPressed: () => context.go(
                        '/home/marketplace/orders/${order.id}/accept',
                      ),
                      child: const Text(
                        'Qabul qilish',
                        style: TextStyle(fontSize: 12),
                      ),
                    ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  String _fmtDate(DateTime dt) {
    String pad2(int n) => n.toString().padLeft(2, '0');
    return '${pad2(dt.day)}.${pad2(dt.month)}.${dt.year} '
        '${pad2(dt.hour)}:${pad2(dt.minute)}';
  }
}
