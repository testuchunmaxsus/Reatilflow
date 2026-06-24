import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

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
          // Filtr: barcha / faol
          Consumer(builder: (context, ref, _) {
            final showAll = ref.watch(_storeDeliveryShowAllProvider);
            return IconButton(
              icon: Icon(
                  showAll ? Icons.filter_list_off : Icons.filter_list),
              tooltip: showAll ? 'Faqat faollar' : 'Hammasi',
              onPressed: () => ref
                  .read(_storeDeliveryShowAllProvider.notifier)
                  .state = !showAll,
            );
          }),
        ],
      ),
      body: storeId == null
          ? const _NoStoreBody()
          : _StoreDeliveryBody(storeId: storeId),
    );
  }
}

// ---------------------------------------------------------------------------

/// Faol/hammasi toggle holati
final _storeDeliveryShowAllProvider =
    StateProvider.autoDispose<bool>((ref) => false);

// ---------------------------------------------------------------------------

class _NoStoreBody extends StatelessWidget {
  const _NoStoreBody();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.local_shipping_outlined,
                size: 64, color: Colors.grey.shade300),
            const SizedBox(height: 16),
            const Text(
              "Do'kon ID topilmadi",
              style: TextStyle(fontWeight: FontWeight.w600, fontSize: 16),
            ),
            const SizedBox(height: 8),
            const Text(
              'Akkauntga do\'kon biriktirilmagan.',
              textAlign: TextAlign.center,
              style: TextStyle(color: Colors.grey),
            ),
          ],
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------

class _StoreDeliveryBody extends ConsumerWidget {
  const _StoreDeliveryBody({required this.storeId});
  final String storeId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final showAll = ref.watch(_storeDeliveryShowAllProvider);

    // Barcha yoki faqat faol yetkazishlar (lokal Drift stream)
    final deliveriesAsync = showAll
        ? ref.watch(deliveriesStreamProvider)
        : ref.watch(activeDeliveriesStreamProvider);

    return deliveriesAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => _ErrorBody(message: e.toString()),
      data: (deliveries) {
        if (deliveries.isEmpty) {
          return _EmptyBody(showAll: showAll);
        }
        return RefreshIndicator(
          onRefresh: () async {}, // SyncNotifier boshqaradi
          child: Column(
            children: [
              // Qisqacha statistika
              _SummaryBanner(deliveries: deliveries),

              // Ro'yxat
              Expanded(
                child: ListView.builder(
                  padding: const EdgeInsets.fromLTRB(12, 8, 12, 16),
                  itemCount: deliveries.length,
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
    final delivering =
        deliveries.where((d) => d.status == 'delivering').length;
    final delivered =
        deliveries.where((d) => d.status == 'delivered').length;
    final failed =
        deliveries.where((d) => d.status == 'failed').length;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      color: Colors.grey.shade50,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceAround,
        children: [
          _StatChip(
            label: 'Yetkazilmoqda',
            value: delivering,
            color: Colors.purple,
          ),
          _StatChip(
            label: 'Yetkazildi',
            value: delivered,
            color: Colors.green,
          ),
          _StatChip(
            label: 'Muvaffaqiyatsiz',
            value: failed,
            color: Colors.red,
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
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          '$value',
          style: TextStyle(
            fontSize: 20,
            fontWeight: FontWeight.bold,
            color: color,
          ),
        ),
        Text(
          label,
          style: const TextStyle(fontSize: 10, color: Colors.grey),
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
    final (color, icon, label) = _statusInfo(delivery.status);

    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: () => context.push(
          '/home/deliveries/${delivery.id}',
        ),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Row(
            children: [
              // Holat ikonasi
              Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  color: color.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Icon(icon, color: color, size: 22),
              ),
              const SizedBox(width: 12),

              // Ma'lumot
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            'Buyurtma: ${delivery.orderId.substring(0, 8)}...',
                            style: const TextStyle(
                                fontWeight: FontWeight.w600,
                                fontSize: 13),
                          ),
                        ),
                        Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 8, vertical: 2),
                          decoration: BoxDecoration(
                            color: color.withValues(alpha: 0.1),
                            borderRadius: BorderRadius.circular(8),
                            border: Border.all(
                                color: color.withValues(alpha: 0.4)),
                          ),
                          child: Text(
                            label,
                            style: TextStyle(
                                color: color,
                                fontSize: 10,
                                fontWeight: FontWeight.w600),
                          ),
                        ),
                      ],
                    ),
                    if (delivery.address != null) ...[
                      const SizedBox(height: 4),
                      Row(
                        children: [
                          const Icon(Icons.location_on_outlined,
                              size: 13, color: Colors.grey),
                          const SizedBox(width: 4),
                          Expanded(
                            child: Text(
                              delivery.address!,
                              style: const TextStyle(
                                  fontSize: 12, color: Colors.grey),
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
                          const Icon(Icons.person_outline,
                              size: 13, color: Colors.grey),
                          const SizedBox(width: 4),
                          Text(
                            delivery.customerName!,
                            style: const TextStyle(
                                fontSize: 12, color: Colors.grey),
                          ),
                        ],
                      ),
                    ],
                  ],
                ),
              ),

              const Icon(Icons.chevron_right, color: Colors.grey, size: 18),
            ],
          ),
        ),
      ),
    );
  }

  (Color, IconData, String) _statusInfo(String status) => switch (status) {
        'assigned' => (Colors.blue, Icons.assignment, 'Tayinlangan'),
        'started' => (Colors.orange, Icons.directions_run, 'Boshlandi'),
        'delivering' => (Colors.purple, Icons.local_shipping, 'Yetkazilmoqda'),
        'delivered' => (Colors.green, Icons.check_circle, 'Yetkazildi'),
        'failed' => (Colors.red, Icons.cancel, 'Muvaffaqiyatsiz'),
        _ => (Colors.grey, Icons.help, status),
      };
}

// ---------------------------------------------------------------------------

class _EmptyBody extends StatelessWidget {
  const _EmptyBody({required this.showAll});
  final bool showAll;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.local_shipping_outlined,
                size: 64, color: Colors.grey.shade300),
            const SizedBox(height: 12),
            Text(
              showAll
                  ? 'Hali yetkazishlar yo\'q'
                  : 'Faol yetkazishlar yo\'q',
              style: Theme.of(context)
                  .textTheme
                  .titleMedium
                  ?.copyWith(color: Colors.grey),
            ),
            const SizedBox(height: 8),
            const Text(
              'Buyurtmalar tayinlangach bu yerda ko\'rinadi.',
              style: TextStyle(color: Colors.grey, fontSize: 13),
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }
}

class _ErrorBody extends StatelessWidget {
  const _ErrorBody({required this.message});
  final String message;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline, color: Colors.red, size: 40),
            const SizedBox(height: 8),
            Text('Xatolik: $message', textAlign: TextAlign.center),
          ],
        ),
      ),
    );
  }
}
