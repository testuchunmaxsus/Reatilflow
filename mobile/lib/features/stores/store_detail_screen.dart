import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../data/local/database.dart';
import 'stores_providers.dart';

/// Do'kon detail ekrani — lokal Drift'dan (offline).
class StoreDetailScreen extends ConsumerWidget {
  const StoreDetailScreen({super.key, required this.storeId});
  final String storeId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final storeAsync = ref.watch(storeByIdProvider(storeId));

    return Scaffold(
      appBar: AppBar(
        title: const Text("Do'kon"),
        actions: [
          IconButton(
            icon: const Icon(Icons.shopping_cart_outlined),
            tooltip: 'Buyurtma',
            onPressed: () =>
                context.push('/home/orders/create?storeId=$storeId'),
          ),
        ],
      ),
      body: storeAsync.when(
        data: (store) {
          if (store == null) {
            return const Center(child: Text("Do'kon topilmadi"));
          }
          return _StoreDetailBody(store: store);
        },
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Xatolik: $e')),
      ),
    );
  }
}

class _StoreDetailBody extends StatelessWidget {
  const _StoreDetailBody({required this.store});
  final Store store;

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Sarlavha
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Row(
                children: [
                  const CircleAvatar(
                    radius: 28,
                    child: Icon(Icons.store, size: 32),
                  ),
                  const SizedBox(width: 16),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          store.name,
                          style:
                              Theme.of(context).textTheme.titleLarge?.copyWith(
                                    fontWeight: FontWeight.bold,
                                  ),
                        ),
                        if (store.address != null) ...[
                          const SizedBox(height: 4),
                          Text(
                            store.address!,
                            style: Theme.of(context)
                                .textTheme
                                .bodyMedium
                                ?.copyWith(color: Colors.grey),
                          ),
                        ],
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),

          const SizedBox(height: 12),

          // GPS koordinatalar
          if (store.gpsLat != null && store.gpsLng != null)
            _InfoRow(
              icon: Icons.location_on_outlined,
              label: 'GPS',
              value:
                  '${store.gpsLat!.toStringAsFixed(6)}, ${store.gpsLng!.toStringAsFixed(6)}',
              valueColor: Colors.blue,
            ),

          // Telefon
          if (store.phone != null)
            _InfoRow(
              icon: Icons.phone_outlined,
              label: 'Telefon',
              value: store.phone!,
            ),

          // INN
          if (store.inn != null)
            _InfoRow(
              icon: Icons.badge_outlined,
              label: 'INN',
              value: store.inn!,
            ),

          // Balans (credit limit)
          if (store.creditLimit != null)
            _InfoRow(
              icon: Icons.account_balance_wallet_outlined,
              label: 'Kredit limiti',
              value: '${_formatAmount(store.creditLimit!)} UZS',
              valueColor: Colors.green,
            ),

          const SizedBox(height: 24),

          // Buyurtma berish tugmasi
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              onPressed: () =>
                  context.push('/home/orders/create?storeId=${store.id}'),
              icon: const Icon(Icons.add_shopping_cart),
              label: const Text('Buyurtma berish'),
            ),
          ),
        ],
      ),
    );
  }

  String _formatAmount(double amount) {
    final parts = amount.toStringAsFixed(0).split('');
    final buffer = StringBuffer();
    for (var i = 0; i < parts.length; i++) {
      if (i > 0 && (parts.length - i) % 3 == 0) buffer.write(' ');
      buffer.write(parts[i]);
    }
    return buffer.toString();
  }
}

class _InfoRow extends StatelessWidget {
  const _InfoRow({
    required this.icon,
    required this.label,
    required this.value,
    this.valueColor,
  });
  final IconData icon;
  final String label;
  final String value;
  final Color? valueColor;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        children: [
          Icon(icon, size: 20, color: Colors.grey),
          const SizedBox(width: 12),
          Text('$label: ',
              style: const TextStyle(
                  color: Colors.grey, fontWeight: FontWeight.w500)),
          Expanded(
            child: Text(
              value,
              style: TextStyle(
                fontWeight: FontWeight.w600,
                color: valueColor,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
