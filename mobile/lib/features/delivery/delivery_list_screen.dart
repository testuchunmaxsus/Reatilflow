import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

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
                padding: const EdgeInsets.all(12),
                child: Badge(
                  label: Text('$active'),
                  child: const Icon(Icons.local_shipping),
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
            return const _EmptyDeliveries();
          }
          return ListView.separated(
            padding: const EdgeInsets.all(16),
            itemCount: deliveries.length,
            separatorBuilder: (_, __) => const SizedBox(height: 8),
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
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Xatolik: $e')),
      ),
    );
  }

  bool _isTerminal(String status) =>
      status == 'delivered' || status == 'failed';
}

class _EmptyDeliveries extends StatelessWidget {
  const _EmptyDeliveries();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            Icons.local_shipping_outlined,
            size: 80,
            color: Colors.grey.shade300,
          ),
          const SizedBox(height: 16),
          Text(
            'Tayinlangan yetkazish yo\'q',
            style: Theme.of(context)
                .textTheme
                .titleMedium
                ?.copyWith(color: Colors.grey),
          ),
          const SizedBox(height: 8),
          const Text(
            'Yetkazishlar sync orqali yuklanadi',
            style: TextStyle(fontSize: 12, color: Colors.grey),
          ),
        ],
      ),
    );
  }
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
    final (statusColor, statusLabel) = _statusInfo(delivery.status);

    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      'Buyurtma: ${delivery.orderId.substring(0, 8)}...',
                      style: const TextStyle(
                          fontWeight: FontWeight.w600, fontSize: 14),
                    ),
                  ),
                  _StatusBadge(
                    color: statusColor,
                    label: statusLabel,
                  ),
                ],
              ),
              if (delivery.address != null) ...[
                const SizedBox(height: 6),
                Row(
                  children: [
                    const Icon(Icons.location_on, size: 14, color: Colors.grey),
                    const SizedBox(width: 4),
                    Expanded(
                      child: Text(
                        delivery.address!,
                        style:
                            const TextStyle(fontSize: 12, color: Colors.grey),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  ],
                ),
              ],
              if (delivery.customerName != null) ...[
                const SizedBox(height: 4),
                Row(
                  children: [
                    const Icon(Icons.person, size: 14, color: Colors.grey),
                    const SizedBox(width: 4),
                    Text(
                      delivery.customerName!,
                      style:
                          const TextStyle(fontSize: 12, color: Colors.grey),
                    ),
                  ],
                ),
              ],
              const SizedBox(height: 8),
              Row(
                children: [
                  const Icon(Icons.schedule, size: 12, color: Colors.grey),
                  const SizedBox(width: 4),
                  Text(
                    _fmtDate(delivery.assignedAt ?? delivery.createdAt),
                    style:
                        const TextStyle(fontSize: 11, color: Colors.grey),
                  ),
                  const Spacer(),
                  // Sync holat indikatori
                  if (delivery.syncStatus == 'pending')
                    const Icon(Icons.pending_outlined,
                        size: 14, color: Colors.orange),
                  if (delivery.syncStatus == 'conflict')
                    const Icon(Icons.warning_amber,
                        size: 14, color: Colors.red),
                  const Icon(Icons.chevron_right,
                      size: 16, color: Colors.grey),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  (Color, String) _statusInfo(String status) => switch (status) {
        'assigned' => (Colors.blue, 'Tayinlangan'),
        'started' => (Colors.orange, 'Boshlandi'),
        'delivering' => (Colors.purple, 'Yetkazilmoqda'),
        'delivered' => (Colors.green, 'Yetkazildi'),
        'failed' => (Colors.red, 'Muvaffaqiyatsiz'),
        _ => (Colors.grey, status),
      };

  String _fmtDate(DateTime dt) =>
      '${dt.day.toString().padLeft(2, '0')}.${dt.month.toString().padLeft(2, '0')} '
      '${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
}

class _StatusBadge extends StatelessWidget {
  const _StatusBadge({required this.color, required this.label});

  final Color color;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withValues(alpha: 0.5)),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: color,
          fontSize: 11,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}
